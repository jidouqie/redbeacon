"""自动化控制：调度器状态、定时任务配置、手动触发。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import config as cfg
import database
import scheduler as sched
from utils.logger import get_logger

router = APIRouter()
logger = get_logger("router.automation")

_DEFAULTS = {
    "auto_generate_enabled":    "true",
    "auto_publish_enabled":     "true",
    "publish_interval_minutes": "15",
}


class AutomationConfig(BaseModel):
    auto_generate_enabled:    bool | None = None
    auto_publish_enabled:     bool | None = None
    publish_interval_minutes: int  | None = None


@router.get("/status")
def get_status():
    return {
        "running": sched.is_running(),
        "jobs":    sched.get_jobs(),
    }


@router.get("/config")
def get_config():
    raw = {k: cfg.get(k, d) for k, d in _DEFAULTS.items()}
    return {
        "auto_generate_enabled":    raw["auto_generate_enabled"].lower() == "true",
        "auto_publish_enabled":     raw["auto_publish_enabled"].lower() == "true",
        "publish_interval_minutes": int(raw["publish_interval_minutes"]),
    }


@router.patch("/config")
def update_config(body: AutomationConfig):
    if body.auto_generate_enabled is not None:
        cfg.set("auto_generate_enabled", "true" if body.auto_generate_enabled else "false")
    if body.auto_publish_enabled is not None:
        cfg.set("auto_publish_enabled", "true" if body.auto_publish_enabled else "false")
    if body.publish_interval_minutes is not None:
        if body.publish_interval_minutes < 5:
            raise HTTPException(400, "发布轮询间隔最少 5 分钟")
        cfg.set("publish_interval_minutes", str(body.publish_interval_minutes))
    sched.restart()
    logger.info("[automation] 配置更新，调度器已重启")
    return {"ok": True}


@router.post("/trigger/{task}")
def trigger_task(task: str):
    c = database.conn()
    accounts = c.execute("SELECT id FROM account").fetchall()
    c.close()

    if task == "publish":
        logger.info("[automation] 手动触发：发布")
        from tasks.publish import run_publish
        total = sum(run_publish(account_id=acc["id"]) for acc in accounts)
        return {"ok": True, "published": total}
    elif task == "generate":
        logger.info("[automation] 手动触发：文案生成")
        from tasks.generate import run_generate
        total = sum(run_generate(account_id=acc["id"]) for acc in accounts)
        return {"ok": True, "generated": total}
    else:
        raise HTTPException(404, f"未知任务：{task}")
