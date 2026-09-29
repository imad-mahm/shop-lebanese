# Shop Lebanese 🌲

A directory of Lebanese online shops and local brands, with product search across all of them. A bot finds new shops by itself every ~10 minutes. It costs **$0** to run: GitHub Actions + GitHub Pages on a public repo.

```
site/            the website (static HTML/CSS/JS, reads site/data/*.json)
bot/             the discovery + catalog bot (Python)
seeds/           starting points: known shops, hub pages, blocklist
data/            the bot's memory (committed by the bot on every run)
.github/         the 10-minute schedule, deploy, and "Add / Remove my shop" forms
```

## How the bot works

Every run (`python -m bot all`) goes through these steps:

1. **Collect candidates** (domains that might be shops) from:
   | Source | What it is |
   |---|---|
   | `seeds/stores.txt` | Shops you already know |
   | `seeds/hubs.txt` | Pages that link to many shops (lists, concept stores, agency portfolios), re-read weekly |
   | **Snowball links** | Every website the bot checks gets its outbound links queued. Shops link to their designers, agencies, partner brands and other shops, so the directory grows by itself. |
   | **Common Crawl** | Walks the public Common Crawl index of every crawled `*.lb` host, one page per run |
   | **Brave Search** (optional) | Rotating searches like "delivery all over Lebanon shop". Free tier; enable with a `BRAVE_API_KEY` secret. |
   | **"Add my shop" issues** | Owners submit their website or Instagram through a GitHub issue form, and the bot processes it on the next run |
2. **Verify** up to 30 candidates (6 at a time). A candidate is listed only if:
   - it's a shop: Shopify, WooCommerce, Magento, OpenCart, Ecomz, or any site with a cart/checkout;
   - it's Lebanese, with a score of 4 or more:
     | Signal | Points |
     |---|---|
     | `.lb` domain | +4 |
     | Shopify store country = LB | +5 |
     | +961 phone or WhatsApp number | +3 |
     | Lebanese places mentioned (Beirut, Jounieh, Achrafieh…) | +2/+3 |
     | "Delivery all over Lebanon" or similar | +2 |
     | Whish/OMT payment | +2 |
     | Arabic place names | +1 |
     | LBP prices | +1 |
   - Web agencies are skipped, but their links are still followed.
3. **Sync catalogs** for the 8 stalest Shopify/WooCommerce shops, using the public `/products.json` and the WooCommerce Store API. Each shop is refreshed daily. A shop that fails 4 times in a row is hidden.
4. **Build** `site/data/*.json` for the website, then commit and deploy.

**Politeness:** the bot identifies itself (`ShopLebaneseBot/1.0 (+repo URL)`), obeys every shop's `robots.txt`, waits at least 1 second between requests to the same site, reads only public pages, and never downloads more than 3 MB per page. Owners can ask to be removed.

## Setup (about 10 minutes, $0)

1. **Create a public GitHub repo** named `shop-lebanese` (public repos get free unlimited Actions minutes, and GitHub Pages is free for them).
2. **Push this folder** as the repo root:
   ```bash
   cd "Plan 2/shop-lebanese"
   git init -b main && git add . && git commit -m "Shop Lebanese"
   git remote add origin https://github.com/<you>/shop-lebanese.git
   git push -u origin main
   ```
3. Repo **Settings → Pages → Source: GitHub Actions**.
4. Repo **Settings → Actions → General → Workflow permissions: Read and write**.
5. **Actions tab → bot → Run workflow** once. After that it runs by itself every 10 minutes. Your site is at `https://<you>.github.io/shop-lebanese/`.
6. Edit `site/config.js`: set `repoUrl` to your repo, and `whishNumber` when you're ready to sell featured spots.
7. *(Optional)* Get a free Brave Search API key and add it under **Settings → Secrets → Actions** as `BRAVE_API_KEY`.

The bot creates the `add-shop`, `remove-shop` and `approved` labels on its first run.

## Day-to-day (a few minutes a week)

| Task | How |
|---|---|
| **Feature a paying shop** | After their Whish payment arrives, add `"theirdomain.com": "2026-12-31"` (end date) to `data/featured.json` and commit. It gets a ★ badge and the top spot until that date. |
| **Remove a shop** | The owner opens a "Remove my shop" issue. Check it's really them, then add the `approved` label. The bot removes the shop and blocks it from being re-added. |
| **Add known shops or hub pages** | Add a line to `seeds/stores.txt` or `seeds/hubs.txt` |
| **Watch the bot** | The Actions tab, or "🤖 What is the bot doing right now?" at the bottom of the site |

## Run locally

```bash
pip install -r requirements.txt
python -m bot all                       # one full run (discover + verify + sync + build)
python -m bot discover --probe-limit 60 # just find and verify
python -m bot build                     # rebuild site/data from data/
cd site && python -m http.server 8000   # open http://localhost:8000
```

Tuning knobs are in `bot/config.py`: run budget, candidates per run, score threshold, and products per store.

## Notes and limits

- GitHub may delay scheduled runs by a few minutes when it's busy, so "every 10 minutes" really means about every 10–20 minutes.
- Instagram-only shops can't be discovered automatically (Instagram forbids scraping), so they come in through the "Add my shop" form and show as *self-submitted*.
- Common Crawl's index server is often busy. The bot simply retries the same page on the next run.
- The site only links out. It never sells anything or takes payments for shops, so no payment license is needed.
