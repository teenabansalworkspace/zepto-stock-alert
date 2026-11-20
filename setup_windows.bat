@echo off
REM One-time setup on Windows: creates the virtual environment and installs everything (all free).
cd /d %~dp0
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
if not exist .env copy .env.example .env
echo.
echo Setup done. Ab .env file kholkar BOT_TOKEN aur ADMIN_IDS bhar dein.
pause
