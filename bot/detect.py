"""Decide whether a domain is a Lebanese online shop, and extract its public profile."""
import html as htmllib
import re
from urllib.parse import urljoin

from . import http
from .categories import categorize
from .config import ACCEPT_SCORE, MAX_OUTBOUND_PER_PAGE
from .domains import ignored, registrable

LB_WORDS = re.compile(
    r"\b(lebanon|liban|lebanese|libanais|beirut|beyrouth|jounieh|saida|sidon|zahle|zahleh|byblos|jbeil|batroun|"
    r"metn|keserwan|kesrouan|achrafieh|ashrafieh|hamra|dbayeh|zalka|antelias|jal el dib|verdun|baabda|aley|"
    r"broummana|nabatieh|tyre|sour)\b|لبنان|بيروت|اللبنانية|لبناني|جونيه|صيدا|زحلة|جبيل|البترون",
    re.I,
)
LB_PHONE = re.compile(r"(?:\+|00)\s?961|(?:wa\.me/|phone=)961|\b961[\s-]?(?:3|70|71|76|78|79|81|1)[\s-]?\d{3}")
LBP = re.compile(r"\bLBP\b|\bL\.L\.?|ل\.ل|ليرة")
LOCAL_PAY = re.compile(r"\bwhish\b|\bomt\b", re.I)
ARABIC_PLACES = re.compile(r"لبنان|بيروت|جونيه|صيدا|زحلة|جبيل|البترون")
DELIVERY_LB = re.compile(
    r"(all over|across|anywhere in|throughout|all regions of|everywhere in) lebanon|deliver(y|ies|ing)? (to|in|within) lebanon|"
    r"livraison (partout )?au liban|توصيل (إلى|الى|ل)?\s?(كل|جميع)? ?(المناطق )?(اللبنانية|لبنان)",
    re.I,
)
AGENCY = re.compile(
    r"web ?(design|development|agency)|e-?commerce (development|agency|solutions)|digital (agency|marketing agency)|"
    r"marketing agency|software (house|company)|seo services|we build (websites|online stores)|app development",
    re.I,
)

PAYMENTS = {
    "cod": re.compile(r"cash on delivery|\bCOD\b|الدفع عند الاستلام|paiement à la livraison", re.I),
    "whish": re.compile(r"\bwhish\b", re.I),
    "omt": re.compile(r"\bomt\b", re.I),
    "card": re.compile(r"\bvisa\b|mastercard|credit card|debit card", re.I),
}

CART = re.compile(
    r"add[\s_-]?to[\s_-]?(?:cart|bag|basket)|أضف إلى السلة|اضف الى السلة|ajouter au panier|/cart\b|/checkout\b", re.I
)

IG_SKIP = {"p", "reel", "reels", "explore", "stories", "accounts", "tv", "sharer", "share", "direct"}
FB_SKIP = {"sharer", "sharer.php", "share.php", "tr", "plugins", "dialog", "groups", "profile.php", "events", "hashtag"}

_TAG_BLOCKS = re.compile(r"<(script|style|select|noscript|svg)\b.*?</\1>", re.I | re.S)
_TAGS = re.compile(r"<[^>]+>")
_HREF = re.compile(r"""href\s*=\s*["']([^"'#]+)["']""", re.I)


def visible_text(page_html):
    t = _TAG_BLOCKS.sub(" ", page_html)
    t = _TAGS.sub(" ", t)
    return re.sub(r"\s+", " ", htmllib.unescape(t))


def meta_content(page_html, key):
    for tag in re.findall(r"<meta\b[^>]*>", page_html, re.I):
        if re.search(r"""(?:property|name)\s*=\s*["']%s["']""" % re.escape(key), tag, re.I):
            m = re.search(r"""content\s*=\s*["']([^"']*)["']""", tag, re.I)
            if m:
                return htmllib.unescape(m.group(1)).strip()
    return ""


def detect_platform(page_html, headers):
    h = page_html.lower()
    if "cdn.shopify.com" in h or "shopify.theme" in h or headers.get("x-shopid"):
        return "shopify"
    if "woocommerce" in h:
        return "woocommerce"
    if "ecomz" in h:
        return "ecomz"
    if "mage/cookies" in h or "magento" in h:
        return "magento"
    if "catalog/view/theme" in h:
        return "opencart"
    has_cart = bool(CART.search(page_html))
    if not has_cart:
        return None
    if "wixstatic.com" in h or "x-wix-request-id" in headers:
        return "wix"
    if "squarespace" in h:
        return "squarespace"
    if "bigcommerce" in h:
        return "bigcommerce"
    return "custom"


def clean_name(raw, domain):
    generic = {"home", "homepage", "home page", "welcome", "online shop", "shop", "store", "official website"}
    parts = [p.strip() for p in re.split(r"\s[|–—-]\s|\s[|]\s?", raw or "") if p.strip()]
    for p in parts:
        if p.lower() not in generic and len(p) <= 60:
            return p
    return domain.split(".")[0].replace("-", " ").title()


def socials(page_html):
    out = {}
    hrefs = _HREF.findall(page_html)
    for href in hrefs:
        m = re.search(r"instagram\.com/([A-Za-z0-9_.]{2,30})", href)
        if m and "ig" not in out and m.group(1).lower() not in IG_SKIP:
            out["ig"] = m.group(1).rstrip(".")
        m = re.search(r"facebook\.com/([A-Za-z0-9_.-]{2,80})", href)
        if m and "fb" not in out and m.group(1).lower() not in FB_SKIP:
            out["fb"] = m.group(1)
        m = re.search(r"tiktok\.com/@([A-Za-z0-9_.]{2,30})", href)
        if m and "tt" not in out:
            out["tt"] = m.group(1)
        m = re.search(r"(?:wa\.me/|whatsapp\.com/send/?\?phone=)\+?(\d{8,15})", href)
        if m and "wa" not in out:
            out["wa"] = m.group(1)
    return out


def find_logo(page_html):
    """Best square-ish logo the site publishes: schema.org logo > apple-touch-icon > biggest favicon."""
    m = re.search(r'"logo"\s*:\s*(?:\{[^}]*?"url"\s*:\s*)?"(https?:[^"]+|/[^"]+)"', page_html)
    if m:
        return m.group(1).replace("\\/", "/")
    best, best_size = None, -1
    for tag in re.findall(r"<link\b[^>]*>", page_html, re.I):
        rel = re.search(r"""rel\s*=\s*["']([^"']+)["']""", tag, re.I)
        href = re.search(r"""href\s*=\s*["']([^"']+)["']""", tag, re.I)
        if not rel or not href or "icon" not in rel.group(1).lower() or "mask-icon" in rel.group(1).lower():
            continue
        size = re.search(r"""sizes\s*=\s*["'](\d+)x\d+""", tag, re.I)
        score = int(size.group(1)) if size else (180 if "apple-touch" in rel.group(1).lower() else 16)
        if score > best_size:
            best, best_size = htmllib.unescape(href.group(1)), score
    return best


def outbound_domains(page_html, own):
    found = []
    for href in _HREF.findall(page_html):
        if not href.startswith(("http://", "https://")):
            continue
        d = registrable(href)
        if d and d != own and not ignored(d) and d not in found:
            found.append(d)
            if len(found) >= MAX_OUTBOUND_PER_PAGE:
                break
    return found


def lebanon_score(domain, text, raw_html, shop_meta):
    score, why = 0, []
    if domain.endswith(".lb"):
        score += 4
        why.append(".lb domain")
    country = (shop_meta or {}).get("country")
    if country == "LB":
        score += 5
        why.append("Shopify country LB")
    elif country:
        score -= 1  # many Lebanese brands run their Shopify company from the UAE/UK
        why.append(f"Shopify country {country}")
    if LB_PHONE.search(raw_html):
        score += 3
        why.append("+961 phone")
    places = {m.group(0).lower() for m in LB_WORDS.finditer(text)}
    if places:
        score += 3 if len(places) >= 3 else 2
        why.append("mentions " + ", ".join(sorted(places)[:4]))
    if ARABIC_PLACES.search(text):
        score += 1
        why.append("Arabic place names")
    if DELIVERY_LB.search(text):
        score += 2
        why.append("delivers in Lebanon")
    if LBP.search(text):
        score += 1
        why.append("LBP prices")
    if LOCAL_PAY.search(text):
        score += 2
        why.append("Whish/OMT")
    return score, why


def _fetch_home(domain):
    for url in (f"https://{domain}/", f"https://www.{domain}/", f"http://{domain}/"):
        try:
            page = http.get(url)
        except http.Blocked:
            return None, "blocked by robots.txt"
        if page and page.ok and page.body:
            return page, None
    return None, "unreachable"


def probe(domain):
    """Returns dict(status=store|rejected|error|alias, reason, score, store?, links, alias_of?)."""
    page, err = _fetch_home(domain)
    if page is None:
        return {"status": "error" if err == "unreachable" else "rejected", "reason": err, "score": 0, "links": []}

    final = registrable(page.url) or domain
    if final != domain:
        if ignored(final):
            return {"status": "rejected", "reason": f"redirects to {final}", "score": 0, "links": []}
        return {"status": "alias", "reason": f"redirects to {final}", "score": 0, "links": [final], "alias_of": final}

    base = page.url
    raw = page.text
    platform = detect_platform(raw, page.headers)
    links = outbound_domains(raw, domain)
    if not platform:
        return {"status": "rejected", "reason": "not a shop (no store platform or cart)", "score": 0, "links": links}

    shop_meta = None
    if platform == "shopify":
        try:
            m = http.get(urljoin(base, "/meta.json"), bucket="shopify", bucket_delay=4.0)
            if m and m.ok:
                shop_meta = m.json()
        except (http.Blocked, ValueError):
            shop_meta = None

    text = visible_text(raw)
    score, why = lebanon_score(domain, text, raw, shop_meta)

    # Borderline: read the contact page too before deciding
    if 1 <= score < ACCEPT_SCORE:
        contact = next((h for h in _HREF.findall(raw) if re.search(r"contact|about|اتصل", h, re.I)), None)
        if contact:
            try:
                cp = http.get(urljoin(base, contact))
            except http.Blocked:
                cp = None
            if cp and cp.ok:
                raw += cp.text
                text += " " + visible_text(cp.text)
                score, why = lebanon_score(domain, text, raw, shop_meta)

    if score < ACCEPT_SCORE:
        return {"status": "rejected", "reason": f"not Lebanese enough (score {score}: {'; '.join(why) or 'no signals'})",
                "score": score, "links": links}

    title = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
    name_raw = (shop_meta or {}).get("name") or meta_content(raw, "og:site_name") or (title.group(1) if title else "")
    desc = (shop_meta or {}).get("description") or meta_content(raw, "og:description") or meta_content(raw, "description")
    if AGENCY.search(f"{name_raw} {desc} {title.group(1) if title else ''}"):
        return {"status": "rejected", "reason": "web/marketing agency, not a shop (its links are still followed)",
                "score": score, "links": links}
    image = meta_content(raw, "og:image") or meta_content(raw, "twitter:image")
    logo = find_logo(raw)

    store = {
        "domain": domain,
        "url": base,
        "name": clean_name(htmllib.unescape(name_raw), domain),
        "desc": re.sub(r"\s+", " ", desc)[:300],
        "image": urljoin(base, image) if image else "",
        "icon": urljoin(base, logo) if logo else "",
        "platform": platform,
        "score": score,
        "why": why,
        "currency": (shop_meta or {}).get("currency", ""),
        "payments": [k for k, rx in PAYMENTS.items() if rx.search(text)],
        "categories": categorize(" ".join([name_raw, desc, text[:20000]])),
        "verified": True,
        **socials(raw),
    }
    return {"status": "store", "reason": "; ".join(why), "score": score, "store": store, "links": links}
