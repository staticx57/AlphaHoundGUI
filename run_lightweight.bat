@echo off
:: The same server as run.bat. AI identification, the nuclide data libraries and the Radiacode support are used only
:: when they are installed, so a lightweight install needs no different start.
ECHO Lightweight mode: the same server as run.bat; whatever is not installed is simply not offered.
ECHO.
call "%~dp0run.bat"
