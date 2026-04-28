"""
RedBeacon 后端入口。
启动时：初始化 DB → 初始化 Logger → 拉起 mcp 进程 → 启动 Scheduler → 挂载路由。
"""
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import database
import scheduler as sched
from utils.logger import init_logger, get_logger
import services.mcp_manager as mcp_manager
from routers import account, content, strategy, settings as settings_router, topics as topics_router, automation as automation_router, debug as debug_router

# ── 数据目录 ───────────────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    # 编译为二进制后，可执行文件所在目录即项目根目录
    _BASE = Path(sys.executable).parent
else:
    _BASE = Path(__file__).parent.parent

DATA_DIR = str(os.environ.get("REDBEACON_DATA_DIR", _BASE / "data"))
LOG_DIR  = str(os.environ.get("REDBEACON_LOG_DIR",  _BASE / "logs"))


# ── 生命周期 ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    init_logger(LOG_DIR)
    logger = get_logger()
    logger.info("RedBeacon 启动中…")

    database.init_db(DATA_DIR)
    logger.info(f"数据库已初始化：{DATA_DIR}")

    sched.start()

    yield  # 应用运行中

    # 关闭
    logger.info("RedBeacon 关闭，停止调度器和所有 mcp 进程…")
    sched.stop()
    mcp_manager.stop_all()


# ── FastAPI 实例 ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="RedBeacon",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000", "http://127.0.0.1:8000",
        "http://localhost:3000", "http://127.0.0.1:3000",  # dev
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 路由 ───────────────────────────────────────────────────────────────────────

app.include_router(account.router,       prefix="/api/accounts", tags=["account"])
app.include_router(content.router,       prefix="/api/content",  tags=["content"])
app.include_router(strategy.router,      prefix="/api/strategy", tags=["strategy"])
app.include_router(topics_router.router, prefix="/api/topics",   tags=["topics"])
app.include_router(settings_router.router,   prefix="/api/settings",   tags=["settings"])
app.include_router(automation_router.router, prefix="/api/automation", tags=["automation"])
app.include_router(debug_router.router,      prefix="/api/debug",      tags=["debug"])


# ── 前端静态文件（Next.js export 后放在 frontend/out/）─────────────────────────
# _BASE 已指向二进制所在目录（frozen）或项目根目录（开发），两种情况路径一致
_FRONTEND = _BASE / "frontend" / "out"
if _FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND), html=True), name="frontend")


# ── 开发启动 ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
