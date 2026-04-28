@echo off

REM Keep window open when double-clicked from Explorer
if not "%1"=="run" (
    cmd /k "%~f0" run
    exit /b
)

title RedBeacon Windows Build

echo ============================================
echo  RedBeacon - Windows Build Script
echo ============================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 goto NO_PYTHON

REM Check Node.js
node --version >nul 2>&1
if errorlevel 1 goto NO_NODE

echo [OK] Python:
python --version
echo [OK] Node.js:
node --version
echo.

REM Step 1: Backend dependencies
echo [1/3] Installing backend dependencies...
pip install -r backend\requirements.txt
if errorlevel 1 goto FAIL

REM Step 2: Frontend dependencies
echo.
echo [2/3] Installing frontend dependencies...
cd frontend
call npm install
if errorlevel 1 (
    cd ..
    goto FAIL
)
cd ..

REM Step 3: Build
echo.
echo [3/3] Building RedBeacon...
python build.py
if errorlevel 1 goto FAIL

echo.
echo ============================================
echo  Build complete!
echo  Output: ..\redbeacon-dist\win\
echo ============================================
goto END

:NO_PYTHON
echo [ERROR] Python not found. Please install Python 3.11+
echo         https://www.python.org/downloads/
goto END

:NO_NODE
echo [ERROR] Node.js not found. Please install Node.js 18+
echo         https://nodejs.org/
goto END

:FAIL
echo.
echo [ERROR] Build failed. See error above.

:END
echo.
pause
