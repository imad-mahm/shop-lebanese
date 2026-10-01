"""Polite HTTP: one identifiable user agent, robots.txt, per-host rate limit, size cap."""
import json
import threading
import time
import urllib.robotparser
from urllib.parse import urlsplit

import requests

from .config import MAX_BYTES, PER_HOST_DELAY, TIMEOUT, UA


class Blocked(Exception):
    """robots.txt disallows this URL for our bot."""


class Page:
    def __init__(self, status, url, headers, body, encoding):
        self.status = status
        self.url = url
        self.headers = headers
        self.body = body
        self.encoding = encoding

    @property
    def ok(self):
        return 200 <= self.status < 300

    @property
    def text(self):
        return self.body.decode(self.encoding or "utf-8", errors="replace")

    def json(self):
        return json.loads(self.body)


_local = threading.local()
_robots = {}
_robots_lock = threading.Lock()
_last_hit = {}
_hit_lock = threading.Lock()


def _session():
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": UA, "Accept-Language": "en,ar;q=0.8,fr;q=0.6"})
        s.max_redirects = 6
        _local.s = s
    return s


def _wait_turn(host, delay=PER_HOST_DELAY):
    with _hit_lock:
        now = time.monotonic()
        slot = max(now, _last_hit.get(host, 0.0) + delay)
        _last_hit[host] = slot
    delay = slot - time.monotonic()
    if delay > 0:
        time.sleep(delay)


def _raw_get(url, timeout, headers=None, bucket=None, bucket_delay=None, max_bytes=MAX_BYTES):
    _wait_turn(urlsplit(url).netloc)
    if bucket:  # e.g. every Shopify store shares one rate limit per visitor IP
        _wait_turn(bucket, bucket_delay or PER_HOST_DELAY)
    try:
        with _session().get(url, timeout=timeout, stream=True, allow_redirects=True, headers=headers) as r:
            body = r.raw.read(max_bytes, decode_content=True)
            ctype = r.headers.get("content-type", "")
            enc = r.encoding if "charset" in ctype.lower() else "utf-8"
            return Page(r.status_code, r.url, r.headers, body, enc)
    except (requests.RequestException, OSError, ValueError):
        return None


def _robots_for(url):
    parts = urlsplit(url)
    base = f"{parts.scheme}://{parts.netloc}"
    with _robots_lock:
        rp = _robots.get(base)
    if rp is not None:
        return rp
    rp = urllib.robotparser.RobotFileParser()
    page = _raw_get(base + "/robots.txt", timeout=10)
    if page is None or page.status >= 500:
        rp.allow_all = True
    elif page.status in (401, 403):
        rp.disallow_all = True
    elif page.status >= 400:
        rp.allow_all = True
    else:
        rp.parse(page.text.splitlines())
    with _robots_lock:
        _robots[base] = rp
    return rp


def get(url, timeout=TIMEOUT, check_robots=True, headers=None, bucket=None, bucket_delay=None, retries=3,
        max_bytes=MAX_BYTES):
    """Return a Page, or None on network failure. Raises Blocked if robots.txt forbids it.

    On HTTP 429 (rate limited) it backs off, honouring Retry-After, and tries again."""
    if check_robots and not _robots_for(url).can_fetch(UA, url):
        raise Blocked(url)
    for attempt in range(retries + 1):
        page = _raw_get(url, timeout, headers, bucket, bucket_delay, max_bytes)
        if page is None or page.status != 429 or attempt == retries:
            return page
        try:
            wait = min(float(page.headers.get("retry-after", "")), 60)
        except ValueError:
            wait = 8 * (attempt + 1)
        time.sleep(wait)
    return page
