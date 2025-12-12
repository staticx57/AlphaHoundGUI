@echo off
echo ========================================
echo AlphaHound GUI - Lightweight Install
echo ========================================
echo.
echo This installs ONLY core dependencies.
echo ML features (PyRIID) will NOT be available.
echo.
echo Installing core packages...
python -m pip install --upgrade pip
python -m pip install fastapi uvicorn python-multipart pyserial websockets matplotlib reportlab numpy scipy pillow pandas becquerel slowapi

echo.
echo ========================================
echo Lightweight Installation Complete!
echo ========================================
echo.
echo To run the app: run_lightweight.bat
echo.
echo Note: ML identification will not be available.
echo To enable ML, run: install.bat
echo.
pause
