# 🖥️ PC Build Price Tracker

Tracks prices for a Ryzen 7 9700X + RTX 5070 build, forecasts the trend, and shows **BUY** or **WAIT** for each part.
Open or refresh the web app to fetch today's prices automatically.

## How prices are fetched
None of these Indian stores offers a public price API, so the app reads public product pages. Each part checks **several sites** and keeps the **lowest in-stock price**. If one site blocks the request or the product is out of stock, the other sites still cover it.

| Part | Sources (in order) |
|---|---|
| CPU, Motherboard | MDComputers, pricehistory.app (Amazon.in), pcpaisa |
| RAM, CPU Cooler | pricehistory.app (Amazon.in) |
| GPU | gpuprix.com (India lowest) |
| SSD | MDComputers, pricehistory.app, pcpricetracker |
| Power Supply, Case | Computech, MDComputers |

Sources live in `parts.json`. To add a source, give it a `url`, a `pattern` (a regex whose first group is the price) and, optionally, a `require` regex such as an in-stock check.

## Files
| File | What it does |
|---|---|
| `app.py` | Streamlit web dashboard. Auto-fetches on page load, cached for 6 hours. |
| `update_prices.py` | Command-line fetcher used by Task Scheduler and GitHub Actions |
| `tracker_core.py` | Fetching and forecast logic |
| `parts.json` | Parts, targets, market outlook and sources |
| `data/prices.csv` | Price history |
| `.github/workflows/update-prices.yml` | Daily cloud update at 09:00 IST |
| `run_tracker.bat`, `setup_windows_task.bat` | Daily update from your Windows PC |

## Setup
1. **GitHub:** push this folder to `aashutosh2102/pc-price-tracker`.
2. **Streamlit:** go to share.streamlit.io → Create app → this repo → `app.py` → Deploy.
3. **Token** (needed to save prices):
   - On GitHub, go to Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token.
   - Set **Repository access** to *Only select repositories* and choose `pc-price-tracker`.
   - Under **Permissions → Repository permissions**, set **Contents** to **Read and write**.
   - In Streamlit, go to App → Settings → Secrets and paste:
     ```toml
     GITHUB_REPO = "aashutosh2102/pc-price-tracker"
     GITHUB_TOKEN = "github_pat_..."
     ```
   - In the app sidebar, open **Check GitHub connection → Run check**. You should see three ✅.
4. **GitHub Actions** (optional): Repo → Settings → Actions → General → Workflow permissions → **Read and write** → Save. Then go to Actions → Update prices → Run workflow.
5. **Windows task** (optional): in your cloned folder, run `pip install requests`, then double-click `setup_windows_task.bat`.

## Commands
```bash
python update_prices.py --test           # show what every site returns, without saving
python update_prices.py                  # fetch and save
python update_prices.py --add GPU 74990  # record a Nehru Place quote
```

## Forecast
1. **Your-data trend:** a straight line through your prices, with recent prices weighted more (half-life of 45 days).
2. **Market outlook:** the industry forecast in `parts.json`. RAM is +8% and SSD +12% per 90 days, from TrendForce's 4Q26 outlook.
3. **Blend:** trust in your data = n/(n+8). With few prices it relies mostly on the market outlook. With many, it relies mostly on your data.
4. **1-year path:** price changes are assumed to halve each quarter.

Forecasts are a guide, not a guarantee. Keep fetching to about once a day, and respect each site's terms.
