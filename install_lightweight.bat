@echo off
setlocal
TITLE Installing AlphaHound GUI (lightweight)
cd /d "%~dp0"

ECHO ========================================
ECHO AlphaHound GUI - Lightweight Install
ECHO ========================================
ECHO.
ECHO This installs only the core packages: the application, analysis, PDF reports and the AlphaHound.
ECHO Left out, and used only if you install them later: AI identification (scikit-learn),
ECHO the nuclide data libraries (the app falls back to its built-in tables; the shielding and
ECHO emissions calculators need curie), other spectrum formats, and the Radiacode device.
ECHO.
call python --version >nul 2>&1
IF ERRORLEVEL 1 GOTO :nopython
call python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
IF ERRORLEVEL 1 GOTO :oldpython

ECHO Installing the core packages. This needs an internet connection.
ECHO.
call python -m pip install --upgrade pip
call python -m pip install -r "%~dp0requirements_lightweight.txt"
IF ERRORLEVEL 1 GOTO :failed

ECHO.
ECHO ========================================
ECHO Installation complete. What this install can do:
ECHO ========================================
call python "%~dp0backend\tools\check_install.py"
ECHO.
ECHO "absent" lines are optional. Start the application with run_lightweight.bat
ECHO To add everything later: install_deps.bat
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
ECHO ========================================

:end
ECHO.
PAUSE
