#!/bin/bash
# RedBeacon 启动脚本
# 生产包：使用编译好的 RedBeaconServer 二进制（无源码）
# 开发环境：使用系统 Python + next dev

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export REDBEACON_DATA_DIR="$SCRIPT_DIR/data"
export REDBEACON_LOG_DIR="$SCRIPT_DIR/logs"
export MCP_BINARY="$SCRIPT_DIR/tools/xiaohongshu-mcp"
export PLAYWRIGHT_BROWSERS_PATH="$SCRIPT_DIR/data/playwright"

mkdir -p "$REDBEACON_DATA_DIR" "$REDBEACON_LOG_DIR"

echo "[RedBeacon] 启动后端 :8000 ..."

if [ -f "$SCRIPT_DIR/RedBeaconServer" ]; then
    # 生产包：直接运行编译二进制
    "$SCRIPT_DIR/RedBeaconServer" &
    BACKEND_PID=$!
else
    # 开发环境：系统 Python + --reload
    export REDBEACON_RENDERER="$SCRIPT_DIR/backend/render_xhs_v2.py"
    cd "$SCRIPT_DIR/backend"
    python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
    BACKEND_PID=$!

    # 开发模式同时启动 Next.js
    if [ -d "$SCRIPT_DIR/frontend/node_modules" ]; then
        echo "[RedBeacon] 开发模式：启动前端 :3000 ..."
        cd "$SCRIPT_DIR/frontend"
        ./node_modules/.bin/next dev --webpack --port 3000 -H 0.0.0.0 &
        FRONTEND_PID=$!
    fi
fi

LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}')
echo "[RedBeacon] 已启动："
echo "  Web UI  http://localhost:8000  (局域网: http://${LAN_IP}:8000)"
echo "  API文档  http://127.0.0.1:8000/docs"
echo ""
echo "按 Ctrl+C 停止"

trap "kill $BACKEND_PID ${FRONTEND_PID:-} 2>/dev/null; exit" INT TERM
wait
