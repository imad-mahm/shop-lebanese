"""Turn any URL/host into the registrable domain we key stores by, and skip non-shops."""
import re
from urllib.parse import urlsplit

# Platforms where each subdomain is a different shop
MULTI_TENANT = ("myshopify.com", "wixsite.com", "square.site", "business.site", "mystrikingly.com", "ueniweb.com")

TWO_LEVEL = {
    "com.lb", "net.lb", "org.lb", "edu.lb", "gov.lb", "mil.lb",
    "co.uk", "org.uk", "com.au", "com.tr", "com.cy", "co.jp", "com.br", "com.eg", "com.sa", "co.ae",
}

# Government, education, NGOs: never shops
SKIP_SUFFIXES = ("gov.lb", "edu.lb", "org.lb", "mil.lb")

# Big platforms / infrastructure that show up as outbound links but are never Lebanese shops
IGNORE = {
    "facebook.com", "fb.com", "fb.me", "instagram.com", "wa.me", "whatsapp.com", "tiktok.com", "twitter.com",
    "x.com", "youtube.com", "youtu.be", "linkedin.com", "pinterest.com", "snapchat.com", "t.me", "telegram.me",
    "threads.net", "google.com", "goo.gl", "g.page", "google.com.lb", "apple.com", "microsoft.com", "bing.com",
    "shopify.com", "shopifycdn.com", "shopify.dev", "wordpress.org", "wordpress.com", "wp.com", "woocommerce.com",
    "wix.com", "wixstatic.com", "squarespace.com", "bigcommerce.com", "magento.com", "opencart.com",
    "cloudflare.com", "jsdelivr.net", "googleapis.com", "gstatic.com", "googletagmanager.com", "gravatar.com",
    "w3.org", "schema.org", "paypal.com", "visa.com", "mastercard.com", "amazon.com", "aliexpress.com",
    "ebay.com", "bit.ly", "linktr.ee", "linkin.bio", "beacons.ai", "trustpilot.com", "github.com",
    "waze.com", "whish.money", "areeba.com", "tap.company", "payoneer.com", "stripe.com", "klaviyo.com",
    "mailchimp.com", "hotjar.com", "yotpo.com", "judge.me", "tawk.to", "zendesk.com", "cdninstagram.com",
    "fbcdn.net", "doubleclick.net", "adobe.com", "creativecommons.org", "elementor.com", "themeforest.net",
    "envato.com", "wikipedia.org", "gnu.org", "php.net", "jquery.com", "fontawesome.com", "fonts.com",
    "typekit.net", "vimeo.com", "spotify.com", "soundcloud.com", "medium.com", "blogspot.com", "tumblr.com",
    "yahoo.com", "outlook.com", "gmail.com", "hotmail.com", "icloud.com", "zoom.us", "calendly.com",
}

_IP = re.compile(r"^[\d.]+$")


def host_of(url_or_host):
    s = url_or_host.strip()
    if not s:
        return None
    if "://" not in s:
        s = "http://" + s
    try:
        host = urlsplit(s).hostname
    except ValueError:
        return None
    return host.lower().strip(".") if host else None


def registrable(url_or_host):
    host = host_of(url_or_host)
    if not host or "." not in host or _IP.match(host):
        return None
    if host.startswith("www."):
        host = host[4:]
    labels = host.split(".")
    for mt in MULTI_TENANT:
        if host.endswith("." + mt):
            return ".".join(labels[-(mt.count(".") + 2):])
    if ".".join(labels[-2:]) in TWO_LEVEL:
        return ".".join(labels[-3:]) if len(labels) >= 3 else None
    return ".".join(labels[-2:])


def ignored(domain):
    if not domain:
        return True
    if domain.endswith(SKIP_SUFFIXES):
        return True
    return any(domain == d or domain.endswith("." + d) for d in IGNORE)
