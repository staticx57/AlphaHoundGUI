@echo off
TITLE AlphaHound GUI - Server
ECHO ========================================
ECHO AlphaHound GUI - N42 Viewer
ECHO ========================================
ECHO.
ECHO Starting server at http://localhost:3200
ECHO.
ECHO NOTE: AlphaHound device is OPTIONAL
ECHO The GUI will work without a connected device
ECHO.
ECHO Press Ctrl+C to stop the server
ECHO ========================================
ECHO.

cd backend

:: Start the FastAPI server
START "" "http://localhost:3200"
python -m uvicorn main:app --reload --host 0.0.0.0 --port 3200

PAUSE
