@echo off
REM InReal: start the app (production server) and a public Cloudflare link to it.
REM Public visitors get a READ-ONLY dashboard. Scraping and n8n keep working from this laptop.
cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
python -c "import waitress" 2>nul || pip install waitress

set "CF=cloudflared"
where cloudflared >nul 2>nul || (
  if exist "%ProgramFiles(x86)%\cloudflared\cloudflared.exe" set "CF=%ProgramFiles(x86)%\cloudflared\cloudflared.exe"
  if exist "%ProgramFiles%\cloudflared\cloudflared.exe" set "CF=%ProgramFiles%\cloudflared\cloudflared.exe"
)

start "InReal app" cmd /k python app.py
timeout /t 5 /nobreak >nul
echo.
echo Your public link is the https://....trycloudflare.com line below. Keep this window open.
echo.
"%CF%" tunnel --url http://127.0.0.1:5000
