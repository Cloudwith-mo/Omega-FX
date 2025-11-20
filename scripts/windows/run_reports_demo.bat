@echo off
setlocal
pushd "%~dp0..\.."
call .\.venv\Scripts\activate.bat >nul
python scripts\run_exec_quarterly_report.py --hours 6 --tag demo --use-latest-session
python scripts\run_daily_exec_report.py --hours 24 --tag demo --use-latest-session
python scripts\build_notification_snapshot.py --tag demo
popd
endlocal
