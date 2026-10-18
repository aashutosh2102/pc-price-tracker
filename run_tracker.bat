@echo off
REM Runs the price tracker and (if this folder is a git repo) pushes new prices to GitHub.
cd /d "%~dp0"
if not exist logs mkdir logs
echo ==== %date% %time% ==== >> logs\tracker.log
if exist .git git pull --rebase --quiet >> logs\tracker.log 2>&1
python update_prices.py >> logs\tracker.log 2>&1
if exist .git (
  git add data\prices.csv
  git diff --cached --quiet || git commit -m "Price update from Windows PC" >> logs\tracker.log 2>&1
  git push --quiet >> logs\tracker.log 2>&1
)
