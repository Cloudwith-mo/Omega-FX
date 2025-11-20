@echo off
setlocal
pushd "%~dp0..\.."
call .\.venv\Scripts\activate.bat >nul
python scripts\run_demo_autopilot.py ^
  --hours 23.5 ^
  --sleep-seconds 10 ^
  --risk_tier conservative
popd
endlocal
