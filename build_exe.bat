@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found.
    echo Follow the setup instructions in README.md first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo PyInstaller is not installed.
    echo Run: .venv\Scripts\python.exe -m pip install -r requirements-dev.txt
    pause
    exit /b 1
)

echo Building terminal-free QR-Scanner.exe...
".venv\Scripts\python.exe" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name QR-Scanner ^
    app.py

if errorlevel 1 (
    echo.
    echo EXE build failed.
    pause
    exit /b 1
)

"dist\QR-Scanner.exe" --self-test
if errorlevel 1 (
    echo.
    echo EXE self-test failed.
    pause
    exit /b 1
)

copy /Y "LICENSE" "dist\LICENSE.txt" >nul
if errorlevel 1 (
    echo.
    echo License copy failed.
    pause
    exit /b 1
)

echo.
echo Build completed: dist\QR-Scanner.exe and dist\LICENSE.txt
exit /b 0
