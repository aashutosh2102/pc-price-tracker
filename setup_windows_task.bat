@echo off
REM Creates a daily Windows task that runs run_tracker.bat at 10:00 AM.
schtasks /Create /TN "PC Price Tracker" /TR "\"%~dp0run_tracker.bat\"" /SC DAILY /ST 10:00 /F
if %errorlevel%==0 (echo Task created. Find it in Task Scheduler as "PC Price Tracker".) else (echo Failed - right-click this file and choose "Run as administrator".)
pause
