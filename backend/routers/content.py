"""内容队列：查询、状态更新、手动触发生成。路由全部以 account_id 参数化。"""
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import database
import config as cfg
from utils.logger import get_logger

router = APIRouter()
logger = get_logger("router.content")

# ── 异步任务 Job Store ──────────────────────────────────────────────────────────

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _new_job() -> str:
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {
            "step": 0, "status": "running",
            "content_id": None, "error": None,
            "_ts": time.time(),
        }
        # 清理超过 1 小时的旧 job
        cutoff = time.time() - 3600
        stale = [k for k, v in _jobs.items() if v["_ts"] < cutoff]
        for k in stale:
            del _jobs[k]
    return job_id


def _update_job(job_id: str, **kwargs):
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)

VALID_STATUSES = {"pending_review", "approved", "rejected", "published", "failed"}


# ── Schema ─────────────────────────────────────────────────────────────────────

class ContentOut(BaseModel):
    id: int
    account_id: int
    topic: str
    content_type: str | None
    pillar_name: str | None
    title: str | None
    body: str | None
    tags: list[str]
    image_prompt: str | None
    images: list[str]
    visual_theme: str | None
    status: str
    review_comment: str | None
    scheduled_at: str | None
    published_at: str | None
    xhs_note_id: str | None
    error_msg: str | None
    created_at: str


class StatusUpdate(BaseModel):
    status: str
    review_comment: str | None = None
    scheduled_at: str | None = None


class ContentEdit(BaseModel):
    title: str | None = None
    body: str | None = None
    tags: list[str] | None = None


class GenerateOptions(BaseModel):
    topic: str | None = None          # 手动指定选题，None = 从选题库取
    content_type: str | None = None   # 指定内容类型，None = 轮询
    image_mode: str | None = None     # "cards" | "ai" | "both"；None = 读账号策略 default_image_mode
    pillar: str | None = None         # 指定内容方向，None = AI 自行决定


# ── 路由 ───────────────────────────────────────────────────────────────────────
# 注意：固定路径路由必须在 /{account_id} 之前定义，否则 FastAPI 会把固定路径当作
# account_id 参数解析并报 int 类型错误。

@router.get("/publish-running")
def publish_running():
    """查询是否有发布任务正在运行。"""
    from tasks.publish import is_publish_running
    return {"running": is_publish_running()}


@router.post("/cancel-publish")
def cancel_publish_task():
    """取消正在运行的发布任务（发送取消信号）。"""
    from tasks.publish import cancel_publish, is_publish_running
    if not is_publish_running():
        return {"ok": True, "cancelled": False, "msg": "没有正在运行的发布任务"}
    cancel_publish()
    logger.info("[cancel-publish] 已发送取消信号")
    return {"ok": True, "cancelled": True, "msg": "已发送取消信号，任务将在当前步骤完成后中止"}


@router.post("/feishu-push")
def feishu_push():
    """将所有未推送的 pending_review 内容推送到飞书。"""
    from tasks.generate import _push_to_feishu
    c = database.conn()
    rows = c.execute(
        "SELECT id FROM content_queue WHERE status='pending_review' AND (feishu_record_id IS NULL OR feishu_record_id='')"
    ).fetchall()
    c.close()
    pushed = 0
    for row in rows:
        try:
            _push_to_feishu(row["id"])
            pushed += 1
        except Exception as e:
            logger.warning(f"[feishu_push] content_id={row['id']} 推送失败: {e}")
    return {"ok": True, "pushed": pushed}


@router.post("/publish-now")
def publish_now():
    """手动触发发布轮询：先同步飞书状态，再发布所有 approved 内容。"""
    try:
        import random as _random
        from tasks.feishu_sync import run_feishu_sync
        from tasks.publish import run_publish
        c = database.conn()
        accounts = c.execute("SELECT id FROM account").fetchall()
        c.close()
        logger.info(f"[publish-now] 手动触发，共 {len(accounts)} 个账号")
        synced = 0
        published = 0
        published_accounts = []   # 记录实际发布过的账号，用于账号间加间隔
        import time as _time
        from tasks.publish import _cancel_flag
        for acc in accounts:
            if _cancel_flag.is_set():
                logger.info("[publish-now] 收到取消信号，中止多账号循环")
                break
            aid = acc["id"]
            # 未开启代理轮换时，上一账号有发布则等待 60-180s 避免同 IP 密集操作
            # 开启代理轮换时每个账号 IP 不同，无需等待
            proxy_rotate = cfg.get("proxy_auto_rotate", "false").lower() == "true"
            if published_accounts and not proxy_rotate:
                wait = _random.randint(60, 180)
                logger.info(f"[publish-now] 账号 {aid}：等待 {wait}s 后开始（多账号间隔）…")
                for _ in range(wait):
                    if _cancel_flag.is_set():
                        break
                    _time.sleep(1)
                if _cancel_flag.is_set():
                    logger.info("[publish-now] 等待中收到取消信号，中止")
                    break
            logger.info(f"[publish-now] 账号 {aid}：开始飞书同步…")
            s = run_feishu_sync(account_id=aid)
            synced += s
            # 检查本地是否有待发布内容
            c2 = database.conn()
            approved_cnt = c2.execute(
                "SELECT COUNT(*) FROM content_queue WHERE account_id=? AND status='approved'",
                (aid,),
            ).fetchone()[0]
            c2.close()
            if approved_cnt == 0:
                logger.info(f"[publish-now] 账号 {aid}：飞书同步完成，更新 {s} 条，无待发布内容，跳过")
                continue
            if _cancel_flag.is_set():
                logger.info(f"[publish-now] 账号 {aid}：发布前收到取消信号，中止")
                break
            logger.info(f"[publish-now] 账号 {aid}：飞书同步完成，更新 {s} 条，有 {approved_cnt} 条待发布，开始发布…")
            p = run_publish(account_id=aid)
            published += p
            if p > 0:
                published_accounts.append(aid)
            logger.info(f"[publish-now] 账号 {aid}：发布完成，本次发布 {p} 条")
        logger.info(f"[publish-now] 全部完成：同步 {synced} 条，发布 {published} 条")
        return {"ok": True, "synced": synced, "published": published}
    except Exception as e:
        logger.error(f"[publish-now] 异常：{e}")
        raise HTTPException(500, str(e))


@router.post("/feishu-sync")
def feishu_sync():
    """手动触发飞书状态同步（拉取飞书审核结果写回本地）。"""
    try:
        from tasks.feishu_sync import run_feishu_sync
        c = database.conn()
        accounts = c.execute("SELECT id FROM account").fetchall()
        c.close()
        total = sum(run_feishu_sync(account_id=acc["id"]) for acc in accounts)
        return {"ok": True, "synced": total}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/feishu-url")
def feishu_url():
    """返回飞书多维表格的访问链接（从 account 表读取）。"""
    c = database.conn()
    acc = c.execute("SELECT feishu_app_token, feishu_table_id FROM account WHERE id=1").fetchone()
    c.close()
    app_token = acc["feishu_app_token"] if acc else None
    table_id  = acc["feishu_table_id"]  if acc else None
    if not app_token:
        return {"url": None}
    url = f"https://www.feishu.cn/base/{app_token}"
    if table_id:
        url += f"?table={table_id}"
    return {"url": url}


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    """轮询生成任务进度。"""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    return {k: v for k, v in job.items() if not k.startswith("_")}


@router.get("/{account_id}", response_model=list[ContentOut])
def list_content(account_id: int, status: str | None = None, limit: int = 20, offset: int = 0):
    c = database.conn()
    if status:
        rows = c.execute(
            "SELECT * FROM content_queue WHERE account_id=? AND status=?"
            " ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (account_id, status, limit, offset),
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT * FROM content_queue WHERE account_id=?"
            " ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (account_id, limit, offset),
        ).fetchall()
    c.close()
    return [_row_to_out(r) for r in rows]


@router.get("/{account_id}/pending", response_model=list[ContentOut])
def list_pending(account_id: int):
    return list_content(account_id, status="pending_review", limit=50)


@router.get("/{account_id}/item/{content_id}", response_model=ContentOut)
def get_content(account_id: int, content_id: int):
    c = database.conn()
    row = c.execute(
        "SELECT * FROM content_queue WHERE id=? AND account_id=?",
        (content_id, account_id),
    ).fetchone()
    c.close()
    if row is None:
        raise HTTPException(404, "内容不存在")
    return _row_to_out(row)


@router.patch("/{account_id}/item/{content_id}/status", response_model=ContentOut)
def update_status(account_id: int, content_id: int, body: StatusUpdate):
    if body.status not in VALID_STATUSES:
        raise HTTPException(400, f"无效状态：{body.status}")
    now = datetime.now(timezone.utc).isoformat()
    c = database.conn()
    c.execute(
        """UPDATE content_queue
           SET status=?, review_comment=?, scheduled_at=COALESCE(?, scheduled_at), updated_at=?
           WHERE id=? AND account_id=?""",
        (body.status, body.review_comment, body.scheduled_at, now, content_id, account_id),
    )
    c.commit()
    row = c.execute(
        "SELECT * FROM content_queue WHERE id=? AND account_id=?",
        (content_id, account_id),
    ).fetchone()
    c.close()
    if row is None:
        raise HTTPException(404, "内容不存在")
    logger.info(f"account={account_id} 内容 {content_id} 状态 → {body.status}")
    return _row_to_out(row)


@router.patch("/{account_id}/item/{content_id}", response_model=ContentOut)
def update_content(account_id: int, content_id: int, body: ContentEdit):
    """编辑内容字段（标题、正文、标签）。"""
    now = datetime.now(timezone.utc).isoformat()
    c = database.conn()
    if body.title is not None:
        c.execute("UPDATE content_queue SET title=?, updated_at=? WHERE id=? AND account_id=?",
                  (body.title.strip(), now, content_id, account_id))
    if body.body is not None:
        c.execute("UPDATE content_queue SET body=?, updated_at=? WHERE id=? AND account_id=?",
                  (body.body.strip(), now, content_id, account_id))
    if body.tags is not None:
        c.execute("UPDATE content_queue SET tags=?, updated_at=? WHERE id=? AND account_id=?",
                  (json.dumps(body.tags, ensure_ascii=False), now, content_id, account_id))
    c.commit()
    row = c.execute("SELECT * FROM content_queue WHERE id=? AND account_id=?",
                    (content_id, account_id)).fetchone()
    c.close()
    if row is None:
        raise HTTPException(404, "内容不存在")
    logger.info(f"account={account_id} 内容 {content_id} 字段已更新")
    return _row_to_out(row)


@router.get("/{account_id}/image")
def serve_image(account_id: int, path: str):
    """直接返回本地图片文件（供前端 <img> 标签使用）。"""
    import os as _os
    data_dir = Path(_os.environ.get("REDBEACON_DATA_DIR", "data")).resolve()
    # 相对路径：拼接 data_dir；绝对路径：直接使用（向后兼容旧记录）
    raw = Path(path)
    p = (data_dir / raw).resolve() if not raw.is_absolute() else raw.resolve()
    # 只允许访问 data 目录下的文件，防止路径穿越
    if not str(p).startswith(str(data_dir)):
        raise HTTPException(403, "路径不在允许范围内")
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "图片不存在")
    suffix = p.suffix.lower()
    media = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}
    return FileResponse(str(p), media_type=media.get(suffix.lstrip("."), "image/png"))


@router.post("/{account_id}/generate")
def trigger_generate(account_id: int, body: GenerateOptions | None = None):
    """手动触发内容生成，立即返回 job_id，后台异步执行。"""
    opts = body or GenerateOptions()

    # 解析 image_mode：调用方未传 → 读账号策略的 default_image_mode → 仍无则 400
    if not opts.image_mode:
        c = database.conn()
        row = c.execute(
            "SELECT data FROM strategy WHERE account_id=? ORDER BY version DESC LIMIT 1",
            (account_id,),
        ).fetchone()
        c.close()
        strategy_data: dict = {}
        if row:
            try:
                strategy_data = json.loads(row["data"])
            except Exception:
                pass
        default_mode = strategy_data.get("default_image_mode")
        if not default_mode:
            raise HTTPException(
                400,
                "image_mode 未指定，且账号未配置 default_image_mode。"
                "请在账号策略中设置默认配图方式（cards / ai / both），或在请求中明确传入 image_mode。"
            )
        opts = opts.model_copy(update={"image_mode": default_mode})

    job_id = _new_job()

    def _run():
        from tasks.generate import run_generate

        def _progress(step: int, data: dict):
            if step < 4:
                _update_job(job_id, step=step)
            else:
                _update_job(job_id, step=step, status="done",
                            content_id=data.get("content_id"))

        try:
            result = run_generate(
                account_id=account_id,
                topic_override=opts.topic,
                content_type_override=opts.content_type,
                image_mode=opts.image_mode,
                pillar_override=opts.pillar,
                progress_cb=_progress,
            )
        except Exception as e:
            logger.error(f"account={account_id} 手动生成失败：{e}")
            _update_job(job_id, status="error", error=str(e))

    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": job_id}


# ── 工具函数 ───────────────────────────────────────────────────────────────────

def _row_to_out(row) -> ContentOut:
    def _parse_json_list(raw) -> list:
        try:
            return json.loads(raw) if raw else []
        except Exception:
            return []

    return ContentOut(
        id=row["id"],
        account_id=row["account_id"],
        topic=row["topic"],
        content_type=row["content_type"] if "content_type" in row.keys() else None,
        pillar_name=row["pillar_name"],
        title=row["title"],
        body=row["body"],
        tags=_parse_json_list(row["tags"] if "tags" in row.keys() else None),
        image_prompt=row["image_prompt"] if "image_prompt" in row.keys() else None,
        images=_parse_json_list(row["images"]),
        visual_theme=row["visual_theme"],
        status=row["status"],
        review_comment=row["review_comment"],
        scheduled_at=row["scheduled_at"],
        published_at=row["published_at"],
        xhs_note_id=row["xhs_note_id"],
        error_msg=row["error_msg"] if "error_msg" in row.keys() else None,
        created_at=row["created_at"],
    )
