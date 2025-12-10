@echo off
TITLE Installing AlphaHound GUI Dependencies
ECHO ========================================
ECHO AlphaHound GUI - Dependency Installer
ECHO ========================================
ECHO.
ECHO Installing required packages...
ECHO This may take a few minutes on first run.
ECHO.

cd backend

:: Install from requirements.txt
pip install -r requirements.txt

ECHO.
ECHO ========================================
IF %ERRORLEVEL%==0 (
    ECHO Installation complete!
    ECHO You can now run the application using run.bat
) ELSE (
    ECHO.
    ECHO WARNING: Some packages may have failed to install.
    ECHO The application may still work if core dependencies installed.
    ECHO.
    ECHO If you see errors when running the app, please check:
    ECHO - Python is properly installed
    ECHO - pip is up to date: python -m pip install --upgrade pip
)
ECHO ========================================
ECHO.
PAUSE
