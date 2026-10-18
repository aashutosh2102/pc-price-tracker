# 🖥️ PC Price Tracker: your build plus the whole market

**Web app tabs**
| Tab | What you get |
|---|---|
| 🎯 **My Build** | Your 8 parts with the BUY/WAIT signal and 90-day and 1-year forecasts. Also shows the **cheapest equivalent in the whole market** for each part, such as any RTX 5070 or any DDR5 32GB 2-stick 6000+ kit. |
| 🛒 **Whole Market** | Every CPU, GPU, motherboard, RAM, SSD, PSU, cooler and case listed in the store categories. Filter, search, view cheapest-per-model or all products, ₹/GB (RAM), ₹/TB (SSD), and ₹ per performance point (GPU). |
| 🆕 **What's New & Deals** | **New models/chips** (for example a new GPU launch), new listings, price drops of 5% or more, all-time lows, and your picks compared with alternatives. |

## How data is collected
None of these stores has a public price API, so the tracker reads their public pages:
- **Your build** (`parts.json` → `sources`): 1–3 sites per part, keeping the lowest in-stock price.
- **Whole market** (`market.json` → `categories`): MDComputers category pages, about 1,300 products and about 15 page loads with a 1-second pause between them. Specs (chip, VRAM, socket, DDR/speed/CL, capacity/gen, watt/rating and so on) are read from product names.
- **History** (`data/market_seen.csv`): the first scan sets the baseline. After that, any product or model never seen before is flagged as **new**.

Add more stores by adding category URLs to `market.json`. The page reader works with most OpenCart and WooCommerce-style product grids.

## Files
| File | Purpose |
|---|---|
| `app.py` | Streamlit dashboard |
| `update_prices.py` / `update_market.py` | Command-line updaters, used by Task Scheduler and GitHub Actions |
| `tracker_core.py` / `market_core.py` | Logic: fetching, spec parsing, forecasting, new and price-drop detection |
| `parts.json` | Your parts, targets, outlook, sources and `match` rules for equivalents |
| `market.json` | Store category URLs, category filters and GPU performance scores |
| `data/` | `prices.csv`, `market_latest.csv`, `market_seen.csv` and `market_meta.json` |

## Commands
```bash
python update_prices.py --test         # check build sources without saving
python update_prices.py                # fetch and save build prices
python update_prices.py --add GPU 74990
python update_market.py --only GPU RAM # test-scan some categories (not saved)
python update_market.py                # full market scan and save
streamlit run app.py                   # run the app locally
```

## Setup
1. Push to GitHub (`aashutosh2102/pc-price-tracker`).
2. **Streamlit Secrets:** `GITHUB_REPO` plus a fine-grained `GITHUB_TOKEN` (this repo only, **Contents: Read and write**). Check it from the sidebar with **Check GitHub connection**.
3. **GitHub Actions:** Settings → Actions → General → Workflow permissions → **Read and write**. It runs daily at 09:00 IST.
4. **Windows:** in your cloned folder, run `pip install requests beautifulsoup4`, then double-click `setup_windows_task.bat` (runs daily at 10:00 AM).

## Notes
- Product names drive the spec parsing, so an odd name can occasionally be categorised wrongly. Use **All products** view to check.
- GPU performance scores (`market.json`) come from gpuprix.com. Only 4 chips are included, and you can add more.
- Keep scans to about once a day and respect each site's terms of use.
