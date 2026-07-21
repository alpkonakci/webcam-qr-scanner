@echo off
setlocal
cd /d "%~dp0"
set "OPENCV_LOG_LEVEL=ERROR"

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found.
    echo Follow the setup instructions in README.md first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" app.py %*

if errorlevel 1 (
    echo.
    echo The application closed with an error.
    pause
)

exit
