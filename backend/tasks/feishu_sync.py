"""
从飞书多维表格拉取审核结果，同步到本地 content_queue。
状态映射：
  飞书「已通过」→ 本地 approved
  飞书「已拒绝」→ 本地 rejected
  飞书「待审核」→ 不变（等用户操作）
同时读取用户在飞书改过的标题/文案/发布时间，写回本地。
"""
from datetime import datetime, timezone, timedelta

import config as cfg
import database
from utils.logger import get_logger

logger = get_logger("tasks.feishu_sync")


def _resolve_schedule_at(raw_value) -> str:
    """
    解析飞书「发布时间」字段（毫秒 Unix 时间戳）。
    1h ≤ delta ≤ 14d → 北京时间 ISO8601；其余 → "" 立即发布。
    """
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


_FEISHU_TO_LOCAL = {
    "通过": "approved",
    "驳回": "rejected",
}


def run_feishu_sync(account_id: int = 1) -> int:
    """
    拉取飞书中所有非「待审核」记录，与本地 feishu_record_id 匹配并更新状态。
    返回本次同步更新的条数。
    """
    app_id     = cfg.get("feishu_app_id")
    app_secret = cfg.get("feishu_app_secret")
    c0 = database.conn()
    acc = c0.execute(
        "SELECT feishu_app_token, feishu_table_id FROM account WHERE id=?", (account_id,)
    ).fetchone()
    c0.close()
    app_token = acc["feishu_app_token"] if acc else None
    table_id  = acc["feishu_table_id"]  if acc else None

    if not all([app_id, app_secret, app_token, table_id]):
        return 0

    try:
        from services.feishu_api import (
            FeishuAPI, FIELD_STATUS, FIELD_TITLE, FIELD_BODY, FIELD_SCHEDULE_AT,
        )
        feishu = FeishuAPI(app_id, app_secret, app_token, table_id)
        records = _fetch_all_records(feishu)
    except Exception as e:
        logger.warning(f"[feishu_sync] 拉取飞书记录失败：{e}")
        return 0

    if not records:
        return 0

    updated = 0
    c = database.conn()
    now = datetime.now(timezone.utc).isoformat()

    for rec in records:
        record_id    = rec.get("record_id")
        fields       = rec.get("fields", {})
        feishu_status = _str(fields.get(FIELD_STATUS))
        local_status  = _FEISHU_TO_LOCAL.get(feishu_status)

        if not record_id or not local_status:
            continue  # 仍是「待审核」或未知状态，跳过

        # 找到本地对应记录（必须是 pending_review 才更新）
        row = c.execute(
            "SELECT id, status FROM content_queue WHERE feishu_record_id=? AND account_id=?",
            (record_id, account_id),
        ).fetchone()
        if row is None or row["status"] not in ("pending_review",):
            continue

        # 读取用户在飞书里改过的标题/文案
        feishu_title = _str(fields.get(FIELD_TITLE))
        feishu_body  = _str(fields.get(FIELD_BODY))
        # 读取定时发布时间（"发布时间"字段，毫秒时间戳）
        schedule_at  = _resolve_schedule_at(fields.get(FIELD_SCHEDULE_AT))

        update_fields = ["status=?", "updated_at=?"]
        update_vals   = [local_status, now]
        if feishu_title:
            update_fields.append("title=?"); update_vals.append(feishu_title)
        if feishu_body:
            update_fields.append("body=?"); update_vals.append(feishu_body)
        # "" → 立即发布（NULL），非空 → 写入北京时间 ISO8601
        update_fields.append("scheduled_at=?"); update_vals.append(schedule_at or None)
        update_vals.append(row["id"])

        c.execute(
            f"UPDATE content_queue SET {', '.join(update_fields)} WHERE id=?",
            update_vals,
        )
        updated += 1
        logger.info(
            f"[feishu_sync] record {record_id} → content_id={row['id']}"
            f" status={local_status} schedule_at={schedule_at or 'immediate'}"
        )

    c.commit()
    c.close()

    if updated:
        logger.info(f"[feishu_sync] 本次同步 {updated} 条")
    return updated


def _fetch_all_records(feishu) -> list[dict]:
    """分页拉取表格所有记录。"""
    import requests
    results = []
    page_token = None

    while True:
        params: dict = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        resp = requests.get(
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{feishu.app_token}/tables/{feishu.table_id}/records",
            headers=feishu._auth(),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        results.extend(data.get("items") or [])
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")

    return results


def _str(val) -> str:
    """飞书字段值可能是字符串、列表（富文本）或 None，统一转成字符串。"""
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, list):
        return "".join(
            seg.get("text", "") for seg in val if isinstance(seg, dict)
        ).strip()
    return str(val).strip()
