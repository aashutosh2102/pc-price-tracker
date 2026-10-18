# 🖥️ PC Build Price Tracker

Tracks prices for a Ryzen 7 9700X + RTX 5070 build, forecasts the trend, and tells you **BUY** or **WAIT** per part.

| File | What it does |
|---|---|
| `app.py` | Streamlit web dashboard |
| `update_prices.py` | Fetches today's prices into `data/prices.csv` |
| `tracker_core.py` | Shared fetching + forecast model |
| `parts.json` | Parts, targets, market outlook, source URLs (edit this) |
| `data/prices.csv` | Price history |
| `.github/workflows/update-prices.yml` | Daily cloud update via GitHub Actions |
| `run_tracker.bat` / `setup_windows_task.bat` | Daily update on your Windows PC |

---

## 1. Run locally (5 min)

```bash
pip install -r requirements.txt
streamlit run app.py
```
Opens at http://localhost:8501.

## 2. Put it on GitHub

1. Create a new repo on github.com, for example `pc-price-tracker`. A **private** repo works too.
2. Upload all files in this folder, keeping the `.github/workflows` folder.

## 3. Host on Streamlit Community Cloud (free)

1. Go to **share.streamlit.io** and sign in with GitHub.
2. **Create app**, then pick your repo, branch `main`, and main file `app.py`. **Deploy**.
3. *(Recommended, so manual quotes are saved permanently)*:
   - On GitHub: **Settings → Developer settings → Fine-grained tokens → Generate**. Limit it to this repo only and set **Contents: Read and write**.
   - In Streamlit: **App → Settings → Secrets** and paste:
     ```toml
     GITHUB_REPO = "your-username/pc-price-tracker"
     GITHUB_TOKEN = "github_pat_..."
     ```

Now just open or refresh your app URL to see the latest prices and forecast.

## 4. Daily automatic updates (choose one or both)

### A. GitHub Actions (cloud, no PC needed)
Already set up in `.github/workflows/update-prices.yml`. It runs daily at 09:00 IST.
- Run it now: **GitHub repo → Actions → Update prices → Run workflow**.
- ⚠️ Some Indian price sites block cloud servers (HTTP 403). If the log shows that, use option B.

### B. Windows Task Scheduler (your PC, more likely to work from an Indian network)
1. Install **Python** (tick *Add Python to PATH*) and **Git for Windows**.
2. Clone your repo: `git clone https://github.com/your-username/pc-price-tracker.git C:\PCTracker`
3. `cd C:\PCTracker` then `pip install requests`
4. Double-click **`setup_windows_task.bat`**. It creates a daily 10:00 AM task. If it fails, right-click it and choose **Run as administrator**.
5. Test it: open **Task Scheduler → Task Scheduler Library → PC Price Tracker →** right-click → **Run**. Then check `logs\tracker.log`.

`run_tracker.bat` fetches the prices, then commits and pushes them to GitHub. Your web app updates automatically.

**Manual setup instead of the .bat:** Task Scheduler → *Create Basic Task* → name it → *Daily* → 10:00 → *Start a program* → Program: `C:\PCTracker\run_tracker.bat`, Start in: `C:\PCTracker` → Finish. Then open the task's **Properties → Settings** and tick *Run task as soon as possible after a scheduled start is missed*.

## 5. Everyday use

| Want to | Do this |
|---|---|
| See prices and signals | Open or refresh the app URL |
| Add a Nehru Place quote | App sidebar → **Add a quote**, or `python update_prices.py --add GPU 74990` |
| Fetch prices right now | App sidebar → **Fetch live prices now** |
| Type prices that couldn't be fetched | `python update_prices.py --ask` |
| Change targets or outlook | Edit `parts.json` in GitHub |

## How the forecast works
1. **Your-data trend:** a weighted straight line through your prices. Recent prices count more (half-life of 45 days by default).
2. **Market outlook:** the industry forecast in `parts.json`. RAM is +8% and SSD +12% per 90 days, from TrendForce's 4Q26 outlook.
3. **Blend:** trust in your data = n/(n+8). With 2 prices it relies mostly on the market outlook. With 30+ prices it relies mostly on your data.
4. **1-year path:** price changes are assumed to halve each quarter, so the forecast doesn't run away.

Forecasts are a guide, not a guarantee. Sudden events like a GPU launch or a sale can't be predicted.

## Notes
- There's **no official price API** for these Indian stores. The app reads their public pages, which can break if a site changes its layout. When that happens, it falls back to manual entry. Keep requests to about once a day and respect each site's terms of use.
- To add a part: add an entry to `parts.json`. `url` and `patterns` are optional. Without them the part is manual-entry only.
