"""
发布任务：直接从飞书读取「通过」状态记录，下载图片，调用 MCP 发布。
流程：飞书「通过」→ 下载图片 → MCP 发布 → 飞书改「已发布」→ 更新本地 DB → 飞书通知。
由 APScheduler 定期轮询触发（每 15-30 分钟一次）。
"""
import os
import re
import time
import random
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

_publish_lock = threading.Lock()
_cancel_flag = threading.Event()


def cancel_publish() -> None:
    """请求取消当前发布任务（非阻塞，设置标志位）。"""
    _cancel_flag.set()


def is_publish_running() -> bool:
    return _publish_lock.locked()

import requests

import database
import config as cfg
import services.mcp_manager as mcp_manager
from utils.logger import get_logger

logger = get_logger("tasks.publish")

MCP_PUBLISH_PATH = "/api/v1/publish"
REQUEST_TIMEOUT = 120

_RETRYABLE_KEYWORDS = [
    "timeout", "connection", "network", "503", "502", "504", "500",
    "timed out", "connection reset", "connection refused",
    "publish_failed", "没有找到", "自动化失败",
]


def _is_retryable_error(msg: str) -> bool:
    m = str(msg).lower()
    return any(kw in m for kw in _RETRYABLE_KEYWORDS)


def _resolve_schedule_at(raw_value) -> str:
    """飞书「发布时间」毫秒时间戳 → CST ISO8601 字符串，或空字符串（立即发布）。"""
    if not raw_value:
        return ""
    try:
        ts_ms = int(raw_value)
        schedule_dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    except Exception:
        return ""
    delta = schedule_dt - datetime.now(timezone.utc)
    if delta < timedelta(hours=1) or delta > timedelta(days=14):
        return ""
    CST = timezone(timedelta(hours=8))
    return schedule_dt.astimezone(CST).isoformat()


def run_publish(account_id: int = 1) -> int:
    """从飞书读取「通过」记录，逐条下载图片并发布。返回本次成功发布数。"""
    if not _publish_lock.acquire(blocking=False):
        logger.warning("[publish] 上一次发布任务仍在运行中，跳过本次触发（防重复发布）")
        return 0
    try:
        if _cancel_flag.is_set():
            logger.info("[publish] 启动前检测到取消信号，跳过")
            return 0
        _cancel_flag.clear()
        return _run_publish_inner(account_id)
    finally:
        _publish_lock.release()


def _run_publish_inner(account_id: int = 1) -> int:
    app_id     = cfg.get("feishu_app_id")
    app_secret = cfg.get("feishu_app_secret")
    c0 = database.conn()
    acc = c0.execute(
        "SELECT feishu_app_token, feishu_table_id, display_name, nickname FROM account WHERE id=?",
        (account_id,),
    ).fetchone()
    c0.close()
    app_token    = acc["feishu_app_token"] if acc else None
    table_id     = acc["feishu_table_id"]  if acc else None
    user_id      = cfg.get("feishu_user_id") or ""
    account_name = (acc["display_name"] or acc["nickname"] or f"账号{account_id}") if acc else f"账号{account_id}"

    if not all([app_id, app_secret, app_token, table_id]):
        logger.warning("[publish] 飞书配置不完整，跳过")
        return 0

    from services.feishu_api import FeishuAPI
    feishu = FeishuAPI(app_id, app_secret, app_token, table_id)

    # 直接从飞书读取「通过」记录
    try:
        records = feishu.get_approved_records()
    except Exception as e:
        logger.error(f"[publish] 读取飞书审核记录失败: {e}")
        return 0

    if not records:
        return 0

    logger.info(f"[publish] 账号 {account_id} 发现 {len(records)} 条待发布")

    # 有待发布内容才检查 MCP 登录状态
    c = database.conn()
    row = c.execute("SELECT mcp_port FROM account WHERE id=?", (account_id,)).fetchone()
    c.close()
    if not row:
        logger.warning(f"[publish] 账号 {account_id} 不存在")
        return 0

    port = row["mcp_port"]

    # 1. 先确保 MCP 在跑（不带代理），再检查登录状态
    headless = cfg.get("mcp_visible", "false").lower() != "true"
    if not mcp_manager.is_running(account_id):
        c2 = database.conn()
        acc2 = c2.execute("SELECT cookie_file FROM account WHERE id=?", (account_id,)).fetchone()
        c2.close()
        cookie_file = acc2["cookie_file"] if acc2 else ""
        if cookie_file:
            try:
                mcp_manager.start(account_id, port, cookie_file, None, headless=headless)
                time.sleep(2)
            except Exception as e:
                logger.warning(f"[publish] 账号 {account_id} MCP 启动失败：{e}")
                return 0

    try:
        _s = requests.Session()
        _s.trust_env = False
        status_resp = _s.get(
            f"{mcp_manager.base_url(port)}/api/v1/login/status",
            timeout=30,
        )
        is_logged_in = status_resp.json().get("data", {}).get("is_logged_in", False)
    except Exception as e:
        logger.warning(f"[publish] 账号 {account_id} MCP 无响应：{e}")
        return 0

    if not is_logged_in:
        logger.warning(f"[publish] 账号 {account_id} 小红书未登录，跳过")
        if user_id:
            try:
                feishu.send_text_message(user_id, f"[{account_name}] 小红书已掉线，请在账号页重新登录")
            except Exception:
                pass
        return 0

    # 2. 登录确认后再换 IP 重启 MCP，代理只用于实际发布
    _setup_fresh_proxy(account_id, port)

    # 准备图片存放根目录
    data_dir = Path(os.environ.get("REDBEACON_DATA_DIR") or cfg.get("data_dir", "data")).resolve()
    img_root = data_dir / "images"
    img_root.mkdir(parents=True, exist_ok=True)

    success = 0
    for record in records:
        if _cancel_flag.is_set():
            logger.info("[publish] 收到取消信号，中止发布")
            break

        record_id = record.get("record_id", "")
        fields    = record.get("fields", {})

        title       = fields.get("标题", "") or ""
        content_raw = fields.get("文案", "") or ""
        tags_raw    = fields.get("标签", "") or ""
        schedule_at = _resolve_schedule_at(fields.get("发布时间"))
        attachments = fields.get("图片", []) or []

        tags = [t.strip() for t in tags_raw.split("、") if t.strip()] if tags_raw else []
        body_clean = re.sub(r'\n+(#[\w\u4e00-\u9fa5 ]+)+$', '', content_raw).strip()

        ok = _publish_one(
            account_id=account_id,
            port=port,
            record_id=record_id,
            title=title,
            body=body_clean,
            tags=tags,
            schedule_at=schedule_at,
            attachments=attachments,
            img_root=img_root,
            feishu=feishu,
            user_id=user_id,
        )
        if ok:
            success += 1

        if record != records[-1] and not _cancel_flag.is_set():
            wait = random.randint(30, 90)
            logger.info(f"[publish] 等待 {wait}s 后继续下一条")
            for _ in range(wait):
                if _cancel_flag.is_set():
                    break
                time.sleep(1)

    mcp_manager.stop(account_id)
    logger.info(f"[publish] 账号 {account_id} 发布完成，MCP 已停止")
    return success


def _publish_one(
    *,
    account_id: int,
    port: int,
    record_id: str,
    title: str,
    body: str,
    tags: list,
    schedule_at: str,
    attachments: list,
    img_root: Path,
    feishu,
    user_id: str | None,
) -> bool:

    # 下载图片到本地
    ts = str(int(time.time()))
    img_dir = img_root / f"publish_{ts}"
    img_dir.mkdir(parents=True, exist_ok=True)
    local_images = []

    try:
        for i, att in enumerate(attachments):
            file_token = att.get("file_token") or att.get("token", "")
            if not file_token:
                continue
            local_path = str(img_dir / f"{ts}_{i}.jpg")
            feishu.download_image(file_token, local_path)
            local_images.append(local_path)
    except Exception as e:
        err = str(e)
        logger.error(f"[publish] 《{title}》图片下载失败：{err}")
        if not _is_retryable_error(err):
            _mark_failed(account_id, record_id, title, err, feishu, user_id)
        return False

    if not local_images:
        logger.warning(f"[publish] 《{title}》无图片，跳过")
        _mark_failed(account_id, record_id, title, "无图片，无法发布图文笔记", feishu, user_id)
        return False

    is_original     = cfg.get("publish_is_original",     "false").lower() == "true"
    is_ai_generated = cfg.get("publish_is_ai_generated", "true").lower() != "false"
    visibility      = cfg.get("publish_visibility", "公开可见") or "公开可见"

    payload: dict = {
        "title":           title[:20],
        "content":         body,
        "images":          local_images,
        "tags":            tags,
        "is_original":     is_original,
        "is_ai_generated": is_ai_generated,
        "visibility":      visibility,
    }
    if schedule_at:
        payload["schedule_at"] = schedule_at

    url = f"{mcp_manager.base_url(port)}{MCP_PUBLISH_PATH}"
    logger.info(f"[publish] 发布《{title}》，定时={schedule_at or '立即'}")

    MAX_ATTEMPTS = 3
    RETRY_DELAYS = [10, 30]  # seconds between attempt 1→2 and 2→3

    last_err = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            _sess = requests.Session()
            _sess.trust_env = False
            resp = _sess.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            last_err = str(e)
            if attempt < MAX_ATTEMPTS and _is_retryable_error(last_err):
                delay = RETRY_DELAYS[attempt - 1]
                logger.warning(f"[publish] 《{title}》网络失败（第{attempt}次），{delay}s 后重试：{last_err}")
                time.sleep(delay)
                continue
            logger.error(f"[publish] 《{title}》网络失败（已重试{attempt-1}次）：{last_err}")
            if not _is_retryable_error(last_err):
                _mark_failed(account_id, record_id, title, last_err, feishu, user_id)
            return False

        try:
            data = resp.json()
        except Exception:
            data = {}

        if not resp.ok or not data.get("success"):
            msg = data.get("details") or data.get("error") or data.get("message") or f"HTTP {resp.status_code}"
            if attempt < MAX_ATTEMPTS and (_is_retryable_error(msg) or _is_retryable_error(str(resp.status_code))):
                delay = RETRY_DELAYS[attempt - 1]
                logger.warning(f"[publish] 《{title}》发布失败（第{attempt}次），{delay}s 后重试：{msg}")
                time.sleep(delay)
                last_err = msg
                continue
            logger.error(f"[publish] 《{title}》发布失败（已重试{attempt-1}次）：{msg}")
            permanent = not _is_retryable_error(msg) and not _is_retryable_error(str(resp.status_code))
            if permanent:
                _mark_failed(account_id, record_id, title, msg, feishu, user_id)
            return False

        break  # success

    # 发布成功
    note_id = data.get("data", {}).get("post_id", "")
    now = datetime.now(timezone.utc).isoformat()

    try:
        feishu.update_record(record_id, {"状态": "已发布"})
    except Exception as e:
        logger.warning(f"[publish] 飞书状态回写失败：{e}")

    c = database.conn()
    c.execute(
        "UPDATE content_queue SET status='published', xhs_note_id=?, published_at=?, updated_at=?"
        " WHERE feishu_record_id=?",
        (note_id, now, now, record_id),
    )
    local = c.execute("SELECT id FROM content_queue WHERE feishu_record_id=?", (record_id,)).fetchone()
    if local:
        c.execute(
            "INSERT INTO publish_log (content_id, account_id, xhs_note_id, status, published_at)"
            " VALUES (?, ?, ?, 'success', ?)",
            (local["id"], account_id, note_id, now),
        )
    c.commit()
    c.close()

    if schedule_at:
        msg = f"《{title}》已提交定时发布（{schedule_at[:16]}）"
    else:
        msg = f"《{title}》已立即发布 ✓"
    logger.info(f"[publish] {msg}")

    if user_id:
        try:
            feishu.send_text_message(user_id, msg)
        except Exception:
            pass

    return True


def _setup_fresh_proxy(account_id: int, port: int) -> None:
    """发布前取一个新 IP 重启 MCP，不存 DB，用完即废。未配置或未开启代理轮换则跳过。"""
    if cfg.get("proxy_auto_rotate", "false").lower() != "true":
        return
    if not cfg.get("proxy_api_url", "").strip():
        return

    from services.proxy_service import fetch_fresh_proxy, test_proxy_speed
    speed_test = cfg.get("proxy_speed_test", "false").lower() == "true"

    new_proxy = None
    for attempt in range(1, 4):
        candidate = fetch_fresh_proxy()
        if not candidate:
            logger.warning(f"[publish] 获取代理 IP 失败（第 {attempt}/3 次）")
            continue
        if not speed_test:
            new_proxy = candidate
            break
        logger.info(f"[publish] 测速代理 IP（第 {attempt}/3 次）：{candidate}")
        if test_proxy_speed(candidate):
            new_proxy = candidate
            break
        logger.warning(f"[publish] 代理 IP 测速不达标，丢弃，尝试换一个")

    if not new_proxy:
        logger.warning(f"[publish] 未找到合格代理 IP，本次发布不使用代理")
        return

    c = database.conn()
    acc = c.execute("SELECT cookie_file FROM account WHERE id=?", (account_id,)).fetchone()
    c.close()
    cookie_file = acc["cookie_file"] if acc else ""

    logger.info(f"[publish] 发布代理：停止 MCP account={account_id}")
    mcp_manager.stop(account_id)
    time.sleep(1)

    headless = cfg.get("mcp_visible", "false").lower() != "true"
    logger.info(f"[publish] 发布代理：以新 IP 启动 MCP account={account_id}")
    mcp_manager.start(account_id, port, cookie_file, new_proxy, headless=headless)

    # 等待 MCP 端口就绪，最多 30 秒
    import socket as _sock
    for _ in range(30):
        try:
            with _sock.socket() as s:
                s.settimeout(1)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    logger.info(f"[publish] 代理轮换完成，新 IP={new_proxy}")
                    return
        except Exception:
            pass
        time.sleep(1)
    logger.warning(f"[publish] 代理轮换：MCP 30s 内未就绪，继续尝试发布")


def _mark_failed(
    account_id: int,
    record_id: str,
    title: str,
    reason: str,
    feishu,
    user_id: str | None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()

    try:
        feishu.update_record(record_id, {"状态": "发布失败"})
    except Exception as e:
        logger.warning(f"[publish] 飞书失败状态回写失败：{e}")

    c = database.conn()
    c.execute(
        "UPDATE content_queue SET status='failed', error_msg=?, updated_at=? WHERE feishu_record_id=?",
        (reason, now, record_id),
    )
    local = c.execute("SELECT id FROM content_queue WHERE feishu_record_id=?", (record_id,)).fetchone()
    if local:
        c.execute(
            "INSERT INTO publish_log (content_id, account_id, status, error_msg, published_at)"
            " VALUES (?, ?, 'failed', ?, ?)",
            (local["id"], account_id, reason, now),
        )
    c.commit()
    c.close()

    if user_id:
        try:
            feishu.send_text_message(
                user_id,
                f"《{title}》发布失败，请在飞书表格中检查后重新设为「通过」重试。\n\n错误：{reason}",
            )
        except Exception:
            pass
