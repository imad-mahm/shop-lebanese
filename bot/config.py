import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PRODUCTS = DATA / "products"
SEEDS = ROOT / "seeds"
SITE_DATA = ROOT / "site" / "data"

REPO_URL = os.environ.get("REPO_URL", "https://github.com/imad-mahm/shop-lebanese")
UA = f"ShopLebaneseBot/1.0 (+{REPO_URL}; directory of Lebanese online shops)"

# HTTP politeness
TIMEOUT = 15
PER_HOST_DELAY = 1.0          # seconds between requests to the same host
MAX_BYTES = 3_000_000         # never download more than this per response

# Per-run budgets (a run happens every ~10 minutes on GitHub Actions)
RUN_BUDGET_SECONDS = float(os.environ.get("BOT_BUDGET", 420))
PROBE_LIMIT = int(os.environ.get("PROBE_LIMIT", 30))
PROBE_WORKERS = 6
SYNC_LIMIT = int(os.environ.get("SYNC_LIMIT", 8))

# Discovery rules
ACCEPT_SCORE = 4              # "Lebanese shop" confidence needed to list a store
RECHECK_REJECTED_DAYS = 60
REFRESH_STORE_DAYS = 7
RETRY_ERROR_HOURS = 24
MAX_TRIES = 3
MAX_OUTBOUND_PER_PAGE = 40
HUB_RECRAWL_DAYS = 7
SEARCH_EVERY_MINUTES = 30     # Brave free tier is 2,000 queries/month

# Catalogs
RESYNC_HOURS = 24
MAX_PRODUCTS_PER_STORE = 3000
CATALOG_SECONDS_PER_STORE = float(os.environ.get("CATALOG_SECONDS", 240))  # stop paging a huge catalog after this; the rest comes next sync
SYNC_WORKERS = 6
DEAD_AFTER_FAILS = 4
