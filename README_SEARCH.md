# 🔎 Search page + automation fixes

## Search any part
New page **Search** (sidebar / top nav). Type naturally: `5070 rtx`, `rtx5070ti`, `9070xt`, `intel 7 ultra cpu`, `9800x3d`, `i5 14400f`, `sn7100 2tb`.
1. **Understands** the query → exact model (asks you to pick when it's ambiguous, e.g. Core Ultra 7 265K / 265KF / 265F / 265).
2. **Finds** the product on gpuprix.com (GPUs), pricehistory.app, pcpricetracker.in and pcpaisa.in, and won't confuse RTX 5070 with 5070 Ti.
3. **Shows** best price now, all-time low/peak, launch date and launch MSRP (GPUs), vs-launch %, rating, the price story chart since launch, a "where today sits" gauge, monthly candles, rating history and the cheapest boards.
4. **⭐ Track daily** saves it to `data/watchlist.json`. `track_searches.py` refreshes it every day, so the price **and rating history** keep growing.

Search uses DuckDuckGo (free, no key). For more reliable results, add a free Google Programmable Search key or a Brave Search key in Secrets (see `.streamlit/secrets.toml.example`).

## Automation fixes
- The schedule runs at :17 instead of :30. GitHub delays or drops scheduled jobs queued at busy times, especially the top of the hour.
- `concurrency` stops two runs from overlapping.
- Each script can fail on its own without stopping the others (`continue-on-error`).
- The push now retries and merges. The bot, your Windows PC and the web app all push to `main`, which previously made pushes fail with "rejected".
- `.gitattributes` uses union merge for the append-only CSV files, so rows from everyone are kept.
- `heartbeat.py` writes `data/last_run.json` and a run summary every time, even when stores block GitHub and no prices change.
