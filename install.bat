@echo off
echo ========================================
echo AlphaHound GUI - Full Install
echo ========================================
echo.
echo This installs ALL dependencies including ML.
echo PyRIID + TensorFlow = ~377MB download
echo.
echo Installing core packages...
python -m pip install --upgrade pip
python -m pip install fastapi uvicorn python-multipart pyserial websockets matplotlib reportlab numpy scipy pillow pandas

echo.
echo Installing PyRIID (Machine Learning)...
echo This may take several minutes...
python -m pip install git+https://github.com/sandialabs/pyriid.git@main

echo.
echo ========================================
echo Full Installation Complete!
echo ========================================
echo.
echo To run the app: run.bat
echo.
pause
