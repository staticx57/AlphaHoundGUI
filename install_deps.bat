@echo off
setlocal
TITLE Installing AlphaHound GUI (full)
cd /d "%~dp0"

ECHO ========================================
ECHO AlphaHound GUI - Full Install
ECHO ========================================
ECHO.
call python --version >nul 2>&1
IF ERRORLEVEL 1 GOTO :nopython
call python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
IF ERRORLEVEL 1 GOTO :oldpython

ECHO Installing every package: the web server, analysis, nuclide data, spectrum formats,
ECHO the Radiacode device support and AI identification.
ECHO This needs an internet connection and takes a few minutes.
ECHO.
call python -m pip install --upgrade pip
call python -m pip install -r "%~dp0backend\requirements.txt"
IF ERRORLEVEL 1 GOTO :failed

ECHO.
ECHO ========================================
ECHO Installation complete. What this install can do:
ECHO ========================================
call python "%~dp0backend\tools\check_install.py"
ECHO.
ECHO Start the application with run.bat
GOTO :end

:nopython
ECHO Python was not found.
ECHO Install Python 3.11 or newer from https://www.python.org/downloads/ and tick
ECHO "Add python.exe to PATH" in its installer, then run this file again.
GOTO :end

:oldpython
call python --version
ECHO AlphaHound GUI needs Python 3.11 or newer (some of its packages require it).
ECHO Install a newer Python from https://www.python.org/downloads/ and run this file again.
GOTO :end

:failed
ECHO.
ECHO ========================================
ECHO Some packages failed to install, so the application may not start. Check:
ECHO  - the internet connection (pip downloads the packages)
ECHO  - that "python -m pip --version" works
ECHO  - the messages above
ECHO Then run this file again, or install_lightweight.bat for the core packages only.
ECHO ========================================

:end
ECHO.
PAUSE
