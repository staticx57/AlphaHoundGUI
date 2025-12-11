@echo off
echo Setting up Python Environment...
cd backend
python -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt
echo Setup Complete! You can now run the viewer using launch.bat in the root folder.
pause
