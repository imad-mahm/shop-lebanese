"""Pull public product catalogs (Shopify /products.json, WooCommerce Store API)."""
import html as htmllib
import re
import time
from urllib.parse import urljoin

from . import http
from .config import CATALOG_SECONDS_PER_STORE, MAX_PRODUCTS_PER_STORE


CATALOG_TIMEOUT = 90          # a 250-product page can be several MB on a slow shop
CATALOG_MAX_BYTES = 25_000_000
SHOPIFY_DELAY = 4.0  # all Shopify stores share one rate limit per visitor, so pace them together


class Transient(Exception):
    """Rate limited / server error / network failure: keep the old catalog and retry next sync."""


def _checked(page):
    if page is None or page.status == 429 or page.status >= 500:
        raise Transient(page.status if page else "network")
    return page


def _num(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def _shopify(base, currency, deadline):
    out = []
    for page_no in range(1, MAX_PRODUCTS_PER_STORE // 250 + 2):
        if time.monotonic() > deadline:
            break
        page = _checked(http.get(urljoin(base, f"/products.json?limit=250&page={page_no}"),
                                 bucket="shopify", bucket_delay=SHOPIFY_DELAY,
                                 timeout=CATALOG_TIMEOUT, max_bytes=CATALOG_MAX_BYTES))
        if not page.ok:
            break  # e.g. 401/404: the store keeps its catalog private
        items = page.json().get("products", [])
        for p in items:
            variants = p.get("variants") or [{}]
            v = variants[0]
            img = (p.get("images") or [{}])[0].get("src", "")
            if img:
                img += ("&" if "?" in img else "?") + "width=400"
            out.append({
                "t": p.get("title", "").strip(),
                "u": urljoin(base, f"/products/{p.get('handle', '')}"),
                "p": _num(v.get("price")),
                "c": _num(v.get("compare_at_price")),
                "cur": currency or "",
                "img": img,
                "type": p.get("product_type", ""),
                "tags": p.get("tags", [])[:8] if isinstance(p.get("tags"), list) else [],
                "in": any(x.get("available", True) for x in variants),
            })
        if len(items) < 250 or len(out) >= MAX_PRODUCTS_PER_STORE:
            break
    return out[:MAX_PRODUCTS_PER_STORE]


def _woo(base, deadline):
    out = []
    for path in ("/wp-json/wc/store/v1/products", "/wp-json/wc/store/products"):
        for page_no in range(1, MAX_PRODUCTS_PER_STORE // 100 + 2):
            if time.monotonic() > deadline:
                break
            page = _checked(http.get(urljoin(base, f"{path}?per_page=100&page={page_no}"),
                                     timeout=CATALOG_TIMEOUT, max_bytes=CATALOG_MAX_BYTES))
            if not page.ok:
                break
            try:
                items = page.json()
            except ValueError:
                break
            if not isinstance(items, list):
                break
            for p in items:
                prices = p.get("prices") or {}
                minor = int(prices.get("currency_minor_unit") or 0)
                div = 10 ** minor

                def money(key):
                    val = _num(prices.get(key))
                    return round(val / div, 2) if val is not None else None

                price, regular = money("price"), money("regular_price")
                img = (p.get("images") or [{}])[0]
                out.append({
                    "t": htmllib.unescape(re.sub(r"<[^>]+>", "", p.get("name", ""))).strip(),
                    "u": p.get("permalink", ""),
                    "p": price,
                    "c": regular if regular and price and regular > price else None,
                    "cur": prices.get("currency_code", ""),
                    "img": img.get("thumbnail") or img.get("src", ""),
                    "type": ", ".join(c.get("name", "") for c in (p.get("categories") or [])[:3]),
                    "tags": [t.get("name", "") for t in (p.get("tags") or [])[:8]],
                    "in": bool(p.get("is_in_stock", True)),
                })
            if len(items) < 100 or len(out) >= MAX_PRODUCTS_PER_STORE:
                break
        if out:
            break
    return out[:MAX_PRODUCTS_PER_STORE]


def fetch(store):
    """Return a product list, [] for platforms without a public catalog, or None on failure."""
    base = store.get("url") or f"https://{store['domain']}/"
    deadline = time.monotonic() + CATALOG_SECONDS_PER_STORE
    try:
        if store.get("platform") == "shopify":
            return _shopify(base, store.get("currency"), deadline)
        if store.get("platform") == "woocommerce":
            return _woo(base, deadline)
    except http.Blocked:
        return []
    except (Transient, ValueError) as e:
        print(f"[sync] {store['domain']}: fetch failed ({type(e).__name__}: {e}); keeping previous catalog")
        return None
    return []
