@echo off
REM Runs the checker on this laptop every 20 minutes (close the window to stop).
cd /d %~dp0
call .venv\Scripts\activate.bat
python main.py loop
pause
