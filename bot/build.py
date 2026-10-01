"""Write the compact JSON files the website reads."""
import json
from datetime import date

from urllib.parse import urlsplit

from .config import SITE_DATA
from .storage import load, load_products, now


def _write(name, obj):
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _short(url, origin):
    """Drop the shop's own origin from product/image URLs; the site re-adds it. Keeps products.json small."""
    return url[len(origin):] if origin and url.startswith(origin + "/") else url


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
        parts = urlsplit(s.get("url", ""))
        origin = f"{parts.scheme}://{parts.netloc}" if parts.netloc else ""
        items = [p for p in load_products(key) if p.get("t") and p.get("u")]
        items.sort(key=lambda p: (not p.get("in", True), not p.get("img")))
        if not out_stores[idx]["img"]:  # no share image published: use the shop's first product photo as banner
            out_stores[idx]["img"] = next((p["img"] for p in items if p.get("img")), "")
        for p in items:
            products.append([idx, p["t"], p.get("p"), p.get("c"), p.get("cur", ""), _short(p.get("img", ""), origin),
                             _short(p["u"], origin), 1 if p.get("in", True) else 0])

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
