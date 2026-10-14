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

if not exist "assets\QR-Scanner.ico" (
    echo Windows application icon not found.
    echo Run: .venv\Scripts\python.exe pwa\scripts\generate_icons.py
    pause
    exit /b 1
)

echo Building terminal-free QR-Scanner.exe for v0.2.0-beta.8-preview.2...
".venv\Scripts\python.exe" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    packaging\QR-Scanner.spec

if errorlevel 1 (
    echo.
    echo EXE build failed.
    pause
    exit /b 1
)

powershell.exe -NoProfile -Command "$p = Start-Process -FilePath 'dist\QR-Scanner.exe' -ArgumentList '--self-test' -WindowStyle Hidden -Wait -PassThru; exit $p.ExitCode"
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

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "package_release.ps1" -Version "v0.2.0-beta.8-preview.2" -AnalysisPath "build\QR-Scanner\Analysis-00.toc"
if errorlevel 1 (
    echo.
    echo Release package creation failed.
    pause
    exit /b 1
)

echo.
echo Build and release package completed in the dist directory.
exit /b 0
