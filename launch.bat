@echo off
TITLE N42 Viewer Launcher
ECHO Starting N42 Viewer...

cd backend

:: Check if venv exists, if not create it
IF NOT EXIST "venv" (
    ECHO Creating virtual environment...
    python -m venv venv
)

:: Activate venv
CALL venv\Scripts\activate

:: Install dependencies (quietly)
ECHO Checking dependencies...
pip install -r requirements.txt > nul 2>&1

:: Start Server
ECHO Starting Server at http://localhost:8080
START "" "http://localhost:8080"
uvicorn main:app --reload --port 8080

PAUSE
