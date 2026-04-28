@echo off
chcp 65001 >nul
setlocal

set DIST_ROOT=..\redbeacon-dist
set DIST=%DIST_ROOT%\win
set EXCLUDE=%~dp0build_exclude.txt

echo Building RedBeacon for Windows...

REM ── 1. Create build venv (pyinstaller + customtkinter only) ──────────────────
if not exist "venv_build" (
    echo Creating build virtual environment...
    python -m venv venv_build
    if errorlevel 1 (
        echo ERROR: python -m venv failed. Make sure Python 3.11+ is installed.
        pause
        exit /b 1
    )
)
set VENV_PY=venv_build\Scripts\python.exe
echo Installing build dependencies...
%VENV_PY% -m pip install --quiet --upgrade pip
%VENV_PY% -m pip install --quiet pyinstaller customtkinter
if errorlevel 1 (
    echo ERROR: Failed to install build dependencies.
    pause
    exit /b 1
)

REM ── 2. Package launcher using build venv ────────────────────────────────────
echo Packaging launcher...
%VENV_PY% -m PyInstaller --name RedBeacon --windowed --onefile --clean --noconfirm launcher.py
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

REM ── 3. Ensure dist directories exist ────────────────────────────────────────
if not exist "%DIST_ROOT%" mkdir "%DIST_ROOT%"
if not exist "%DIST%" mkdir "%DIST%"

REM ── 4. Sync backend (skip __pycache__ and .pyc) ──────────────────────────────
echo Syncing backend...
if exist "%DIST%\backend" rmdir /s /q "%DIST%\backend"
xcopy /e /i /q /exclude:"%EXCLUDE%" backend "%DIST%\backend" >nul

REM ── 5. Sync frontend (skip node_modules and .next) ───────────────────────────
echo Syncing frontend...
if exist "%DIST%\frontend" rmdir /s /q "%DIST%\frontend"
xcopy /e /i /q /exclude:"%EXCLUDE%" frontend "%DIST%\frontend" >nul

REM ── 6. npm install in dist/win/frontend if node_modules missing ──────────────
if not exist "%DIST%\frontend\node_modules" (
    echo Running npm install...
    pushd "%DIST%\frontend"
    npm install
    if errorlevel 1 (
        echo ERROR: npm install failed.
        popd
        pause
        exit /b 1
    )
    popd
)

REM ── 7. Create runtime Python environment with all backend dependencies ────────
echo Creating runtime Python environment...
if exist "%DIST%\python_env" rmdir /s /q "%DIST%\python_env"
python -m venv "%DIST%\python_env"
if errorlevel 1 (
    echo ERROR: Failed to create runtime venv.
    pause
    exit /b 1
)
set RUNTIME_PY=%DIST%\python_env\Scripts\python.exe
echo Installing backend dependencies into runtime environment...
%RUNTIME_PY% -m pip install --quiet --upgrade pip
%RUNTIME_PY% -m pip install --quiet -r backend\requirements.txt
%RUNTIME_PY% -m pip install --quiet httpx playwright
if errorlevel 1 (
    echo ERROR: Failed to install backend dependencies.
    pause
    exit /b 1
)

REM ── 8. Install Playwright Chromium into dist/data/playwright/ ─────────────────
echo Installing Playwright Chromium...
if not exist "%DIST%\data" mkdir "%DIST%\data"
set PLAYWRIGHT_BROWSERS_PATH=%DIST%\data\playwright
if not exist "%PLAYWRIGHT_BROWSERS_PATH%" mkdir "%PLAYWRIGHT_BROWSERS_PATH%"
%RUNTIME_PY% -m playwright install chromium
if errorlevel 1 (
    echo Playwright install failed.
    pause
    exit /b 1
)
set PLAYWRIGHT_BROWSERS_PATH=

REM ── 9. Copy start scripts (Windows only) ────────────────────────────────────
if exist start.bat copy /y start.bat "%DIST%\start.bat" >nul
if exist start_win.py copy /y start_win.py "%DIST%\start_win.py" >nul

REM ── 10. Ensure data and logs dirs exist ─────────────────────────────────────
if not exist "%DIST%\data" mkdir "%DIST%\data"
if not exist "%DIST%\logs" mkdir "%DIST%\logs"

REM ── 11. Copy skills to dist root (shared across platforms) ───────────────────
echo Copying skills...
if exist "%DIST_ROOT%\.claude\commands" rmdir /s /q "%DIST_ROOT%\.claude\commands"
if not exist "%DIST_ROOT%\.claude" mkdir "%DIST_ROOT%\.claude"
xcopy /e /i /q .claude\commands "%DIST_ROOT%\.claude\commands" >nul

REM ── 12. Copy launcher to dist/win/ ──────────────────────────────────────────
echo Copying launcher...
copy /y dist\RedBeacon.exe "%DIST%\RedBeacon.exe"

REM ── 13. Cleanup PyInstaller intermediate files ───────────────────────────────
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
del /q *.spec 2>nul

echo.
echo Build complete: %DIST%
echo Run: RedBeacon.exe
pause
endlocal
