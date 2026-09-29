"""JSON files in data/, written one entry per line so git diffs stay small."""
import json
from datetime import datetime, timezone

from .config import DATA, PRODUCTS, SEEDS


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def age_hours(iso):
    if not iso:
        return float("inf")
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds() / 3600


def load(name, default):
    path = DATA / name
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save(name, obj):
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / name
    if isinstance(obj, dict):
        lines = [f"{json.dumps(k, ensure_ascii=False)}: {json.dumps(obj[k], ensure_ascii=False, sort_keys=True)}"
                 for k in sorted(obj)]
        text = "{\n" + ",\n".join(lines) + "\n}\n"
    else:
        text = json.dumps(obj, ensure_ascii=False, indent=1) + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")


def product_path(domain):
    return PRODUCTS / f"{domain}.json"


def load_products(domain):
    path = product_path(domain)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def save_products(domain, items):
    PRODUCTS.mkdir(parents=True, exist_ok=True)
    text = json.dumps(items, ensure_ascii=False, indent=0) + "\n"
    path = product_path(domain)
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")


def delete_products(domain):
    path = product_path(domain)
    if path.exists():
        path.unlink()


def read_list(name):
    path = SEEDS / name
    if not path.exists():
        return []
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


def append_list(name, value):
    path = SEEDS / name
    existing = read_list(name)
    if value not in existing:
        with path.open("a", encoding="utf-8") as f:
            f.write(value + "\n")
