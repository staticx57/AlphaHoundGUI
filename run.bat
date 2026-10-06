@echo off
setlocal
TITLE AlphaHound GUI
cd /d "%~dp0backend"

call python --version >nul 2>&1
IF ERRORLEVEL 1 GOTO :nopython
call python tools\check_install.py --quiet
IF ERRORLEVEL 1 GOTO :notinstalled

:: Already running? Open it instead of starting a second server (the port would be refused).
netstat -ano | findstr /R /C:":3200 .*LISTENING" >nul
IF NOT ERRORLEVEL 1 GOTO :running

ECHO ========================================
ECHO AlphaHound GUI
ECHO ========================================
ECHO.
ECHO Starting the server at http://localhost:3200 (loading takes up to half a minute).
ECHO From another computer on this network: http://THIS-COMPUTER-ADDRESS:3200
ECHO The AlphaHound and Radiacode devices are optional: the GUI works without them.
ECHO.
ECHO The browser opens when the server is ready. Press Ctrl+C to stop the server.
ECHO For development with automatic restarts (this drops a connected device):
ECHO   python -m uvicorn main:app --reload --port 3200
ECHO ========================================
ECHO.

:: Open the browser when the server answers, not before: it needs a while to load. The server is asked at 127.0.0.1 because
:: "localhost" takes two seconds a request on some Windows setups (IPv6 first); the browser still opens localhost, where its saved
:: settings and history live.
START "" /B powershell -NoProfile -Command "for ($i = 0; $i -lt 120; $i++) { try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 http://127.0.0.1:3200/ | Out-Null; Start-Process http://localhost:3200; break } catch { Start-Sleep -Seconds 1 } }"

call python main.py
GOTO :end

:running
ECHO AlphaHound GUI is already running: opening http://localhost:3200
START "" "http://localhost:3200"
GOTO :end

:nopython
ECHO Python was not found. Run install_deps.bat (or install_lightweight.bat) first;
ECHO it explains how to install Python 3.11 or newer.
GOTO :end

:notinstalled
ECHO The installation is incomplete or Python is too old (see above).
ECHO Run install_deps.bat (everything) or install_lightweight.bat (core packages only).

:end
ECHO.
PAUSE
