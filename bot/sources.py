"""Where new candidate shops come from. Each source calls enqueue(url_or_domain, source_name)."""
import json
import os
import re
from urllib.parse import quote

from . import http
from .config import HUB_RECRAWL_DAYS, SEARCH_EVERY_MINUTES
from .detect import outbound_domains
from .domains import registrable
from .storage import age_hours, now, read_list

GITHUB_API = "https://api.github.com"


def seeds(enqueue):
    return sum(enqueue(line, "seed") for line in read_list("stores.txt"))


def hubs(state, enqueue):
    """Pages that link to many Lebanese shops (lists, concept stores, agency portfolios)."""
    seen = state.setdefault("hubs", {})
    added = 0
    for url in read_list("hubs.txt"):
        if age_hours(seen.get(url)) < HUB_RECRAWL_DAYS * 24:
            continue
        try:
            page = http.get(url)
        except http.Blocked:
            page = None
        seen[url] = now()
        if page and page.ok:
            own = registrable(url)
            links = outbound_domains(page.text, own)
            added += sum(enqueue(d, f"hub:{own}") for d in links)
    return added


def commoncrawl(state, enqueue):
    """Walk the Common Crawl URL index for *.lb hosts, one page per run.

    This is Common Crawl's documented public CDX API (its robots.txt only keeps search engines off the
    HTML pages), so robots is not checked here. One request per run keeps the load negligible."""
    cc = state.setdefault("cc", {"done": [], "cur": None, "page": 0, "pages": None})
    base = "https://index.commoncrawl.org"
    if not cc["cur"]:
        info = http.get(f"{base}/collinfo.json", timeout=30, check_robots=False)
        if not info or not info.ok:
            return 0
        todo = [c["id"] for c in info.json()[:8] if c["id"] not in cc["done"]]
        if not todo:
            return 0
        cc.update(cur=todo[0], page=0, pages=None)
    index = f"{base}/{cc['cur']}-index?url=*.lb&output=json&fl=url"
    if cc["pages"] is None:
        r = http.get(index + "&showNumPages=true", timeout=60, check_robots=False)
        if not r or not r.ok:
            return 0
        try:
            cc["pages"] = int(r.json()["pages"])
        except (ValueError, KeyError):
            return 0
    r = http.get(f"{index}&page={cc['page']}", timeout=150, check_robots=False)
    if not r or not r.ok:
        return 0  # the index is often busy; retry this page next run
    added = 0
    for line in r.text.splitlines():
        if line.startswith("{"):
            try:
                added += enqueue(json.loads(line)["url"], "commoncrawl")
            except (ValueError, KeyError):
                pass
    cc["page"] += 1
    if cc["page"] >= cc["pages"]:
        cc["done"].append(cc["cur"])
        cc.update(cur=None, page=0, pages=None)
    return added


SEARCH_QUERIES = [
    '"delivery all over Lebanon" shop', '"cash on delivery" Lebanon online shop', '"Whish" payment online store Lebanon',
    "Lebanese brand online store", "made in Lebanon shop online", "Beirut online boutique", "Lebanon handmade jewelry shop",
    "Lebanon skincare online store", "Lebanon perfume online shop", "Lebanon home decor online store",
    "Lebanon gifts delivery online", "Lebanon chocolate online order", "Lebanon kids clothing online store",
    "Lebanon abaya online shop", "Lebanon swimwear brand", "Lebanese designer online shop", "متجر الكتروني لبنان توصيل",
    "توصيل لكل لبنان متجر", "boutique en ligne Liban livraison", "Lebanon pet shop online", "Lebanon supplements online store",
    "Lebanon flowers delivery online", "Lebanon candles brand", "Lebanon ceramics shop", "Lebanon stationery online shop",
]


def brave(state, enqueue):
    """Optional: Brave Search API free tier. Set BRAVE_API_KEY as a repo secret to enable."""
    key = os.environ.get("BRAVE_API_KEY")
    s = state.setdefault("search", {"i": 0, "last": None})
    if not key or age_hours(s["last"]) * 60 < SEARCH_EVERY_MINUTES:
        return 0
    q = SEARCH_QUERIES[s["i"] % len(SEARCH_QUERIES)]
    offset = (s["i"] // len(SEARCH_QUERIES)) % 5
    s["i"] += 1
    s["last"] = now()
    r = http.get(
        f"https://api.search.brave.com/res/v1/web/search?q={quote(q)}&country=LB&count=20&offset={offset}",
        check_robots=False, headers={"X-Subscription-Token": key, "Accept": "application/json"},
    )
    if not r or not r.ok:
        return 0
    results = r.json().get("web", {}).get("results", [])
    return sum(enqueue(x.get("url", ""), "search") for x in results)


# ---- GitHub issues: "Add my shop" and approved "Remove my shop" requests ----

def _gh(method, path, body=None):
    import requests
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return None
    try:
        r = requests.request(method, f"{GITHUB_API}/repos/{repo}{path}", json=body, timeout=20,
                             headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        return r.json() if r.ok and r.content else None
    except (requests.RequestException, ValueError):
        return None


def parse_issue_form(body):
    fields = {}
    for block in re.split(r"^###\s+", body or "", flags=re.M)[1:]:
        title, _, value = block.partition("\n")
        value = value.strip()
        fields[title.strip().lower()] = "" if value in ("_No response_", "None") else value
    return fields


LABELS = {"add-shop": "0e8a16", "remove-shop": "d93f0b", "approved": "5319e7"}


def ensure_labels(state):
    """Create the issue labels the forms rely on (once per repo)."""
    if state.get("labels_ok") or not os.environ.get("GITHUB_TOKEN"):
        return
    for name, color in LABELS.items():
        _gh("POST", "/labels", {"name": name, "color": color})
    state["labels_ok"] = True


def open_issues(label):
    return _gh("GET", f"/issues?state=open&labels={quote(label)}&per_page=50") or []


def close_issue(number, comment):
    _gh("POST", f"/issues/{number}/comments", {"body": comment})
    _gh("PATCH", f"/issues/{number}", {"state": "closed"})
