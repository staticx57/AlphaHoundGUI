@echo off
TITLE AlphaHound GUI Launcher (Direct Mode)
ECHO Starting AlphaHound GUI (without venv)...
ECHO.

cd backend

:: Check if required packages are installed
ECHO Checking dependencies...
python -c "import fastapi, uvicorn" 2>nul
IF %ERRORLEVEL% NEQ 0 (
    ECHO Installing required dependencies...
    ECHO This may take a moment...
    ECHO.
    pip install fastapi uvicorn python-multipart numpy scipy matplotlib pyserial websockets reportlab
    IF %ERRORLEVEL% NEQ 0 (
        ECHO.
        ECHO ERROR: Failed to install dependencies
        ECHO Please ensure Python and pip are installed correctly
        PAUSE
        EXIT /B 1
    )
    ECHO.
    ECHO Dependencies installed successfully!
)

:: Optional: Check for becquerel (may fail, but non-critical)
python -c "import becquerel" >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    ECHO.
    ECHO NOTE: becquerel not installed - some CSV parsing features may be limited
    ECHO Install with: pip install becquerel
    ECHO.
)

:: Start Server
ECHO.
ECHO ========================================
ECHO Starting Server at http://localhost:8080
ECHO ========================================
ECHO.
ECHO NOTE: AlphaHound device is optional
ECHO The GUI will start without a connected device
ECHO.
START "" "http://localhost:8080"
python -m uvicorn main:app --reload --port 8080

PAUSE
