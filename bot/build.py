"""Write the compact JSON files the website reads."""
import json
from datetime import date

from .config import INDEX_PRODUCTS_PER_STORE, SITE_DATA
from .storage import load, load_products, now


def _write(name, obj):
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def build():
    stores = load("stores.json", {})
    featured = load("featured.json", {})
    runs = load("runs.json", [])
    today = date.today().isoformat()

    visible = [s for s in stores.values() if not s.get("dead")]
    visible.sort(key=lambda s: s.get("found", ""), reverse=True)

    out_stores, products = [], []
    for s in visible:
        key = s["domain"]
        feat_until = featured.get(key, "")
        out_stores.append({
            "id": key,
            "n": s.get("name", key),
            "d": s.get("desc", ""),
            "url": s.get("url", ""),
            "img": s.get("image", ""),
            "ico": s.get("icon", ""),
            "cats": s.get("categories", []),
            "plat": s.get("platform", ""),
            "pay": s.get("payments", []),
            "ig": s.get("ig", ""), "fb": s.get("fb", ""), "tt": s.get("tt", ""), "wa": s.get("wa", ""),
            "cnt": s.get("product_count", 0),
            "found": s.get("found", "")[:10],
            "ver": s.get("verified", False),
            "feat": feat_until >= today,
        })
        idx = len(out_stores) - 1
        items = [p for p in load_products(key) if p.get("t") and p.get("u")]
        items.sort(key=lambda p: (not p.get("in", True), not p.get("img")))
        for p in items[:INDEX_PRODUCTS_PER_STORE]:
            products.append([idx, p["t"], p.get("p"), p.get("c"), p.get("cur", ""), p.get("img", ""), p["u"],
                             1 if p.get("in", True) else 0])

    candidates = load("candidates.json", {})
    status_counts = {}
    for c in candidates.values():
        status_counts[c["status"]] = status_counts.get(c["status"], 0) + 1

    _write("stores.json", out_stores)
    _write("products.json", products)
    _write("meta.json", {
        "updated": now(),
        "stores": len(out_stores),
        "products": sum(s["cnt"] for s in out_stores),
        "candidates": status_counts,
        "runs": runs[-12:],
    })
    return len(out_stores), len(products)
