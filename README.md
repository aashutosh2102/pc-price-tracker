# ◆ PC Price Tracker

A dark, minimal dashboard for a Ryzen 7 9700X + RTX 5070 build and the whole Indian PC-parts market around it, with each product's **full price history from launch to today**.

## The five views
| Tab | What's inside |
|---|---|
| **Overview** | KPI cards · signal board (price, signal, sparkline per part) · target→today waterfall · cost donut · distance-to-target bullets · whole-build forecast fan · cheaper equivalents |
| **Timeline** | Price journey per product: launch marker, launch MSRP, 12-month median, all-time low/high, your target, forecast cone and 3M/6M/1Y/All zoom · monthly candlesticks · data sources · compare journeys (indexed or ₹, log scale) · GPUs since launch (MSRP → 12-mo low/median → today) |
| **Market** | Market map treemap · value chart per category (GPU perf vs ₹, RAM ₹/GB vs speed vs CL, SSD ₹/TB, PSU ₹ vs watts) · brand share · price spread per model · price distribution · per-model daily history |
| **Pulse** | New models/chips · launch radar · biggest drops · market price index and daily heat map · your picks vs the field |
| **Data** | Fetch logs, targets/outlook editor, CSV downloads |

## Where history comes from
| Source | File | Coverage |
|---|---|---|
| Your build tracker | `data/prices.csv` | Daily, from your first run |
| Long-run history | `data/history.csv` | Seeded with real points back to 2023 (pricehistory.app, pcpricetracker, gpuprix). `backfill_history.py` adds each product's full drop log from pricehistory.app. |
| Launch info | `data/launch.json` | Launch date, MSRP and 12-month low/median for 4 GPUs (gpuprix.com) |
| Market history | `data/market_history.csv` | Every listing's price, stored only when it changes (stays small) |

## Commands
```bash
streamlit run app.py
python update_prices.py      # build prices
python update_market.py      # whole-market scan
python backfill_history.py   # long-run history from pricehistory.app (--test to preview)
```
The Windows task (`run_tracker.bat`) and the GitHub Action run all three every day.

## Setup
1. Push to `aashutosh2102/pc-price-tracker`.
2. **Streamlit Secrets:** `GITHUB_REPO` and `GITHUB_TOKEN` (fine-grained token, this repo only, **Contents: Read and write**).
3. **GitHub Actions:** Settings → Actions → General → Workflow permissions → Read and write.
4. **Windows:** run `pip install -r requirements.txt`, then `setup_windows_task.bat`.

## Customise
- **Theme:** `.streamlit/config.toml` (colours) and `viz.py` (`PALETTE`, `CSS`).
- **Parts, targets and match rules:** `parts.json`. Use `history_item` and `history_urls` to link a part to long-run history.
- **Launch data and GPU performance scores:** `data/launch.json` and `market.json`.

Forecasts are a guide, not a guarantee.
