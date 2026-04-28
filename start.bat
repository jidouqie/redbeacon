@echo off
REM RedBeacon 启动脚本 (Windows)
REM 生产包：使用编译好的 RedBeaconServer.exe 二进制
REM 开发环境：使用系统 Python + next dev

setlocal

set SCRIPT_DIR=%~dp0
set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%

set REDBEACON_DATA_DIR=%SCRIPT_DIR%\data
set REDBEACON_LOG_DIR=%SCRIPT_DIR%\logs
set MCP_BINARY=%SCRIPT_DIR%\tools\xiaohongshu-mcp.exe
set PLAYWRIGHT_BROWSERS_PATH=%SCRIPT_DIR%\data\playwright

if not exist "%REDBEACON_DATA_DIR%" mkdir "%REDBEACON_DATA_DIR%"
if not exist "%REDBEACON_LOG_DIR%" mkdir "%REDBEACON_LOG_DIR%"

echo [RedBeacon] 启动后端 :8000 ...

if exist "%SCRIPT_DIR%\RedBeaconServer.exe" (
    REM 生产包：直接运行编译二进制
    start /B "" "%SCRIPT_DIR%\RedBeaconServer.exe"
) else (
    REM 开发环境：系统 Python + --reload
    set REDBEACON_RENDERER=%SCRIPT_DIR%\backend\render_xhs_v2.py
    cd /d "%SCRIPT_DIR%\backend"
    start /B "" python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

    REM 开发模式同时启动 Next.js
    if exist "%SCRIPT_DIR%\frontend\node_modules" (
        echo [RedBeacon] 开发模式：启动前端 :3000 ...
        cd /d "%SCRIPT_DIR%\frontend"
        start /B "" node_modules\.bin\next dev --webpack --port 3000 -H 0.0.0.0
    )
)

echo [RedBeacon] 已启动：
echo   Web UI  http://localhost:8000
echo   API文档  http://127.0.0.1:8000/docs
echo.
echo 关闭此窗口即停止服务

endlocal
pause
