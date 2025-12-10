@echo off
setlocal
pushd "%~dp0..\.."
call .\.venv\Scripts\activate.bat >nul
python scripts\send_notification_snapshot.py --tag demo
popd
endlocal
