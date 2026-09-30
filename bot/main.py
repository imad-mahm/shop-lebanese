"""Shop Lebanese bot.

    python -m bot discover   find new candidate shops and verify a batch of them
    python -m bot sync       refresh product catalogs of the stalest shops
    python -m bot build      write site/data/*.json for the website
    python -m bot all        all of the above (what GitHub Actions runs every 10 minutes)
"""
import argparse
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import catalog, sources
from .build import build
from .categories import categorize
from .config import (DEAD_AFTER_FAILS, MAX_TRIES, PROBE_LIMIT, PROBE_WORKERS, RECHECK_REJECTED_DAYS,
                     RESYNC_HOURS, RETRY_ERROR_HOURS, RUN_BUDGET_SECONDS, SYNC_LIMIT)
from .detect import probe
from .domains import ignored, registrable
from .storage import (age_hours, append_list, delete_products, load, now, read_list, save, save_products)

SOURCE_PRIORITY = ["submission", "seed", "hub", "link", "search", "commoncrawl"]


class Bot:
    def __init__(self):
        self.started = time.monotonic()
        self.state = load("state.json", {})
        self.cands = load("candidates.json", {})
        self.stores = load("stores.json", {})
        self.blocklist = set(read_list("blocklist.txt"))
        self.log = {"at": now(), "new_candidates": 0, "probed": 0, "new_stores": [], "synced": 0, "sources": {}}

    def time_left(self):
        return RUN_BUDGET_SECONDS - (time.monotonic() - self.started)

    # ---------- queue ----------
    def enqueue(self, url_or_domain, src, **extra):
        d = registrable(url_or_domain)
        if not d or ignored(d) or d in self.blocklist or d in self.cands:
            return 0
        self.cands[d] = {"src": src, "found": now(), "status": "new", "tries": 0, **extra}
        return 1

    def _due(self, c):
        if c["status"] == "new":
            return True
        if c["status"] == "error":
            return c["tries"] < MAX_TRIES and age_hours(c.get("checked")) >= RETRY_ERROR_HOURS
        if c["status"] == "rejected":
            return age_hours(c.get("checked")) >= RECHECK_REJECTED_DAYS * 24
        return False

    def _priority(self, item):
        _, c = item
        kind = c["src"].split(":")[0]
        rank = SOURCE_PRIORITY.index(kind) if kind in SOURCE_PRIORITY else len(SOURCE_PRIORITY)
        return (rank, c.get("found", ""))

    # ---------- discover ----------
    def run_sources(self):
        for name, fn in (("seeds", lambda: sources.seeds(self.enqueue)),
                         ("submissions", self.handle_submissions),
                         ("removals", self.handle_removals),
                         ("hubs", lambda: sources.hubs(self.state, self.enqueue)),
                         ("search", lambda: sources.brave(self.state, self.enqueue)),
                         ("commoncrawl", lambda: sources.commoncrawl(self.state, self.enqueue))):
            if self.time_left() < 60:
                break
            try:
                n = fn()
            except Exception as e:  # one broken source must never stop the bot
                print(f"[{name}] failed: {e!r}", file=sys.stderr)
                n = 0
            self.log["sources"][name] = n
            self.log["new_candidates"] += n
            print(f"[{name}] +{n} candidates")

    def probe_batch(self, limit=PROBE_LIMIT):
        due = sorted((i for i in self.cands.items() if self._due(i[1])), key=self._priority)[:limit]
        if not due:
            return
        with ThreadPoolExecutor(PROBE_WORKERS) as pool:
            futures = {pool.submit(probe, d): d for d, _ in due}
            for fut in as_completed(futures):
                d = futures[fut]
                try:
                    res = fut.result()
                except Exception as e:
                    res = {"status": "error", "reason": repr(e)[:200], "score": 0, "links": []}
                self.apply_probe(d, res)
                if self.time_left() < 30:
                    for f in futures:
                        f.cancel()
                    break

    def apply_probe(self, d, res):
        c = self.cands[d]
        c.update(status=res["status"], reason=res["reason"][:300], score=res["score"], checked=now(),
                 tries=c["tries"] + 1)
        self.log["probed"] += 1
        linked = sum(self.enqueue(link, f"link:{d}") for link in res.get("links", []))
        self.log["new_candidates"] += linked
        self.log["sources"]["links"] = self.log["sources"].get("links", 0) + linked
        if res["status"] == "rejected" and d in self.stores and self.stores[d].get("verified"):
            self.stores.pop(d)  # a re-check showed it is no longer a Lebanese shop
            delete_products(d)
        if res["status"] == "alias":
            target = self.cands.get(res["alias_of"])
            if target and c.get("submitted"):
                target.update(src=c["src"], submitted=c["submitted"])
            return
        if res["status"] != "store":
            return
        store = res["store"]
        old = self.stores.get(d, {})
        extra = c.get("submitted", {})
        # What the owner typed in the "Add my shop" form beats what we scraped
        merged = {**old, **store, **{k: v for k, v in extra.items() if v}}
        merged["found"] = old.get("found") or now()
        merged["checked"] = now()
        merged.pop("dead", None)
        self.stores[d] = merged
        if not old:
            self.log["new_stores"].append(d)
            print(f"  + NEW STORE {d}: {store['name']} ({res['reason']})")

    # ---------- GitHub issue submissions ----------
    def handle_submissions(self):
        sources.ensure_labels(self.state)
        added = 0
        for issue in sources.open_issues("add-shop"):
            f = sources.parse_issue_form(issue.get("body", ""))
            website = f.get("website", "")
            ig = re.sub(r"^@|.*instagram\.com/|/.*$", "", f.get("instagram", "")).strip()
            submitted = {k: v for k, v in {
                "name": f.get("shop name", ""), "desc": f.get("description", "")[:300], "ig": ig,
                "wa": re.sub(r"\D", "", f.get("whatsapp", "")),
            }.items() if v}
            d = registrable(website) if website else None
            if d:
                if ignored(d) or d in self.blocklist:
                    sources.close_issue(issue["number"], f"🤖 **{d}** can't be listed (not a shop domain, or removed on request).")
                    continue
                self.cands.pop(d, None)  # re-check now, even if it was rejected before
                self.enqueue(d, "submission", issue=issue["number"], submitted=submitted)
                res = probe(d)
                self.apply_probe(d, res)
                if res["status"] == "alias" and res["alias_of"] not in self.stores:
                    d = res["alias_of"]
                    self.cands.pop(d, None)
                    self.enqueue(d, "submission", issue=issue["number"], submitted=submitted)
                    res = probe(d)
                    self.apply_probe(d, res)
                ok = d in self.stores
                msg = (f"✅ **{self.stores[d]['name']}** is now listed. Thank you!" if ok else
                       f"🤖 The bot couldn't confirm **{d}** is a Lebanese online shop ({res['reason']}). "
                       "Make sure your site mentions Lebanon or a +961 number and has a shop/cart, then submit again.")
                sources.close_issue(issue["number"], msg)
                added += ok
            elif ig:
                key = f"instagram.com/{ig.lower()}"
                cat = f.get("category", "")
                self.stores.setdefault(key, {
                    "domain": key, "url": f"https://instagram.com/{ig}", "name": submitted.get("name", ig),
                    "desc": submitted.get("desc", ""), "platform": "instagram", "ig": ig, "wa": submitted.get("wa", ""),
                    "categories": [cat] if cat and cat != "Other" else categorize(submitted.get("desc", "")),
                    "payments": [], "verified": False, "found": now(), "checked": now(),
                })
                sources.close_issue(issue["number"], f"✅ **@{ig}** is now listed as an Instagram shop (self-submitted).")
                self.log["new_stores"].append(key)
                added += 1
            else:
                sources.close_issue(issue["number"], "Please include a website or an Instagram handle so we can list your shop.")
        return added

    def handle_removals(self):
        """Removal requests are applied only after the repo owner adds the 'approved' label."""
        removed = 0
        for issue in sources.open_issues("remove-shop"):
            labels = {l["name"] for l in issue.get("labels", [])}
            if "approved" not in labels:
                continue
            f = sources.parse_issue_form(issue.get("body", ""))
            target = f.get("website or instagram", "") or f.get("website", "")
            key = registrable(target) if "instagram.com" not in target else f"instagram.com/{target.rstrip('/').split('/')[-1].lower()}"
            if key:
                self.stores.pop(key, None)
                delete_products(key)
                self.cands.setdefault(key, {"src": "removed", "found": now(), "tries": 0})["status"] = "removed"
                append_list("blocklist.txt", key)
                self.blocklist.add(key)
                removed += 1
            sources.close_issue(issue["number"], f"🗑️ Removed **{key}** from the directory and blocked the bot from re-adding it.")
        return removed

    # ---------- catalogs ----------
    def sync(self, limit=SYNC_LIMIT):
        due = [s for s in self.stores.values()
               if s.get("platform") in ("shopify", "woocommerce") and age_hours(s.get("synced")) >= RESYNC_HOURS]
        due.sort(key=lambda s: s.get("synced") or "")
        for s in due[:limit]:
            if self.time_left() < 20:
                break
            items = catalog.fetch(s)
            if items is None or (not items and s.get("product_count")):
                s["fails"] = s.get("fails", 0) + 1
                if s["fails"] >= DEAD_AFTER_FAILS:
                    s["dead"] = True
            else:
                s.update(fails=0, product_count=len(items))
                s.pop("dead", None)
                save_products(s["domain"], items)
                if items:
                    text = " ".join(f"{p['t']} {p.get('type', '')} {' '.join(p.get('tags', []))}" for p in items)
                    s["categories"] = categorize(text) or s.get("categories", [])
                    if not s.get("currency"):
                        s["currency"] = items[0].get("cur", "")
            s["synced"] = now()
            self.log["synced"] += 1
            print(f"[sync] {s['domain']}: {s.get('product_count', 0)} products")

    # ---------- persistence ----------
    def save(self):
        for d in [d for d, s in self.stores.items()
                  if s.get("verified") and self.cands.get(d, {}).get("status") in ("rejected", "removed")]:
            self.stores.pop(d)
            delete_products(d)
        save("state.json", self.state)
        save("candidates.json", self.cands)
        save("stores.json", self.stores)
        runs = load("runs.json", [])
        self.log["seconds"] = round(time.monotonic() - self.started)
        self.log["total_stores"] = len(self.stores)
        runs = (runs + [self.log])[-200:]
        save("runs.json", runs)


def main(argv=None):
    sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["discover", "sync", "build", "all"])
    ap.add_argument("--probe-limit", type=int, default=PROBE_LIMIT)
    ap.add_argument("--sync-limit", type=int, default=SYNC_LIMIT)
    args = ap.parse_args(argv)

    if args.command == "build":
        print("built: %d stores, %d products in index" % build())
        return

    bot = Bot()
    try:
        if args.command in ("discover", "all"):
            bot.run_sources()
            bot.probe_batch(args.probe_limit)
        if args.command in ("sync", "all"):
            bot.sync(args.sync_limit)
    finally:
        bot.save()
    if args.command == "all":
        print("built: %d stores, %d products in index" % build())
    log = bot.log
    print(f"done in {log['seconds']}s: +{log['new_candidates']} candidates, {log['probed']} probed, "
          f"{len(log['new_stores'])} new stores, {log['synced']} catalogs synced, {log['total_stores']} stores total")


if __name__ == "__main__":
    main()
