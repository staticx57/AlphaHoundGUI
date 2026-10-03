@echo off
echo ========================================
echo AlphaHound GUI - Full Install
echo ========================================
echo.
echo This installs ALL dependencies including ML.
echo AI identification uses scikit-learn (small download)
echo.
echo Installing core packages...
python -m pip install --upgrade pip
python -m pip install fastapi uvicorn python-multipart pyserial websockets matplotlib reportlab numpy scipy pillow pandas slowapi

echo.
echo Installing scikit-learn (AI identification)...
python -m pip install scikit-learn

echo.
echo ========================================
echo Full Installation Complete!
echo ========================================
echo.
echo To run the app: run.bat
echo.
pause
