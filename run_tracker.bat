@echo off
REM Daily: build prices + whole-market scan + long-run history backfill, then push to GitHub.
cd /d "%~dp0"
if not exist logs mkdir logs
echo ==== %date% %time% ==== >> logs\tracker.log
if exist .git git pull --rebase --quiet >> logs\tracker.log 2>&1
python update_prices.py >> logs\tracker.log 2>&1
python update_market.py >> logs\tracker.log 2>&1
python backfill_history.py >> logs\tracker.log 2>&1
if exist .git (
  git add data
  git diff --cached --quiet || git commit -m "Price + market update from Windows PC" >> logs\tracker.log 2>&1
  git push --quiet >> logs\tracker.log 2>&1
)
