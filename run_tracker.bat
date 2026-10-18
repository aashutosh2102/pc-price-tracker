@echo off
REM Daily: build prices + market scan + history backfill + tracked searches, then push to GitHub.
cd /d "%~dp0"
if not exist logs mkdir logs
echo ==== %date% %time% ==== >> logs\tracker.log
if exist .git git pull --no-rebase --no-edit -X ours origin main >> logs\tracker.log 2>&1
python update_prices.py > logs\run.log 2>&1
python update_market.py >> logs\run.log 2>&1
python backfill_history.py >> logs\run.log 2>&1
python track_searches.py >> logs\run.log 2>&1
python heartbeat.py logs\run.log >> logs\run.log 2>&1
type logs\run.log >> logs\tracker.log
if exist .git (
  git add data
  git diff --cached --quiet || git commit -m "Auto update from Windows PC" >> logs\tracker.log 2>&1
  git pull --no-rebase --no-edit -X ours origin main >> logs\tracker.log 2>&1
  git push origin HEAD:main >> logs\tracker.log 2>&1
)
