"""
APScheduler 定时任务。
在 main.py 的 lifespan 里启动，跟随进程生命周期。
所有间隔和开关均从 settings 表读取，修改后调用 restart() 生效。
"""
import json
import random

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import config as cfg
import database
from utils.logger import get_logger

logger = get_logger("scheduler")

_scheduler: BackgroundScheduler | None = None

_JOB_NAMES = {
    "publish_poll": "发布轮询",
    "mcp_health":   "MCP 健康检查",
}


def start() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        return
    _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    _build_jobs()
    _scheduler.start()
    logger.info("[scheduler] 定时任务已启动")


def stop() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[scheduler] 定时任务已停止")


def restart() -> None:
    """配置变更后重建（调用后立即生效）。"""
    stop()
    start()


def is_running() -> bool:
    return bool(_scheduler and _scheduler.running)


def get_jobs() -> list[dict]:
    if not _scheduler or not _scheduler.running:
        return []
    jobs = []
    for j in _scheduler.get_jobs():
        name = _JOB_NAMES.get(j.id)
        if not name:
            if j.id.startswith("generate_acc"):
                parts = j.id.split("_")
                acc_id = parts[1].replace("acc", "") if len(parts) > 1 else "?"
                name = f"自动生成（账号 {acc_id}）"
            else:
                name = j.id
        jobs.append({
            "id": j.id,
            "name": name,
            "next_run": j.next_run_time.strftime("%m-%d %H:%M") if j.next_run_time else "-",
        })
    return sorted(jobs, key=lambda x: x["next_run"])


def _build_jobs() -> None:
    auto_generate   = cfg.get("auto_generate_enabled",        "true").lower() != "false"
    auto_publish    = cfg.get("auto_publish_enabled",         "true").lower() != "false"
    try:
        publish_minutes = max(5, int(cfg.get("publish_interval_minutes", "15") or "15"))
    except (ValueError, TypeError):
        publish_minutes = 15
        logger.warning("[scheduler] publish_interval_minutes 配置无效，使用默认值 15 分钟")

    c = database.conn()
    accounts = c.execute(
        "SELECT id, auto_generate_enabled, generate_schedule_json FROM account"
    ).fetchall()
    c.close()

    if auto_generate:
        enabled_count = 0
        for acc in accounts:
            if acc["auto_generate_enabled"]:
                _add_generate_jobs_for_account(acc["id"], acc["generate_schedule_json"] or "")
                enabled_count += 1
        logger.info(f"[scheduler] 自动生成：全局已启用，{enabled_count}/{len(accounts)} 个账号参与")
    else:
        logger.info("[scheduler] 自动生成：全局已关闭")

    if auto_publish:
        jitter = random.randint(0, 900)
        _scheduler.add_job(
            _run_publish_all,
            IntervalTrigger(minutes=publish_minutes, jitter=jitter),
            id="publish_poll",
            replace_existing=True,
        )
        logger.info(f"[scheduler] 发布轮询：每 {publish_minutes} 分钟（含随机抖动）")
    else:
        logger.info("[scheduler] 发布轮询：已关闭")



def _add_generate_jobs_for_account(account_id: int, schedule_json: str = "") -> None:
    """按账号自身的 generate_schedule_json 建立生成任务，支持三种模式。"""
    import json as _json
    sched_cfg: dict = {}
    if schedule_json:
        try:
            sched_cfg = _json.loads(schedule_json)
        except Exception:
            pass

    mode = sched_cfg.get("mode", "frequency")

    if mode == "interval":
        # 固定间隔：每 N 小时生成一次
        hours = max(1, int(sched_cfg.get("interval_hours", 8)))
        _scheduler.add_job(
            lambda aid=account_id: _run_generate(aid),
            IntervalTrigger(hours=hours),
            id=f"generate_acc{account_id}_interval",
            replace_existing=True,
        )
        logger.info(f"[scheduler] account {account_id} 生成任务：每 {hours} 小时")

    elif mode == "times":
        # 指定时间点：每天在指定时间点生成
        times: list[str] = sched_cfg.get("times", ["09:00"])
        days:  list[int] = sched_cfg.get("days", list(range(7)))
        day_of_week_str = ",".join(str(d) for d in days) if days else "*"
        for i, t in enumerate(times):
            try:
                h, m = map(int, t.split(":"))
            except Exception:
                continue
            _scheduler.add_job(
                lambda aid=account_id: _run_generate(aid),
                CronTrigger(day_of_week=day_of_week_str, hour=h, minute=m),
                id=f"generate_acc{account_id}_t{i}",
                replace_existing=True,
            )
        day_names = ["一","二","三","四","五","六","日"]
        days_str = "、".join(f"周{day_names[d]}" for d in days) if days else "每天"
        logger.info(f"[scheduler] account {account_id} 生成任务：{days_str} {' / '.join(times)}")

    else:
        # frequency 模式：每周 N 篇，随机分配到不同天
        weekly_count = int(sched_cfg.get("weekly_count", 0))
        if weekly_count <= 0:
            # 兜底：从 strategy 表读取
            c = database.conn()
            row = c.execute(
                "SELECT posting_freq FROM strategy WHERE account_id=? ORDER BY version DESC LIMIT 1",
                (account_id,),
            ).fetchone()
            c.close()
            weekly_count = _parse_weekly_count(row["posting_freq"] if row else "每周2篇")
        if weekly_count <= 0:
            return
        selected_days = sorted(random.sample(range(7), min(weekly_count, 7)))
        day_names_full = ["周一","周二","周三","周四","周五","周六","周日"]
        for i, dow in enumerate(selected_days):
            hour   = random.randint(8, 22)
            minute = random.randint(0, 59)
            _scheduler.add_job(
                lambda aid=account_id: _run_generate(aid),
                CronTrigger(day_of_week=dow, hour=hour, minute=minute),
                id=f"generate_acc{account_id}_{i}",
                replace_existing=True,
            )
            logger.info(f"[scheduler] account {account_id} 生成任务 {i+1}：{day_names_full[dow]} {hour:02d}:{minute:02d}")


def _parse_weekly_count(freq: str) -> int:
    import re
    m = re.search(r"(\d+)", freq)
    return int(m.group(1)) if m else 2


# ── 任务执行函数 ────────────────────────────────────────────────────────────────

def _run_generate(account_id: int) -> None:
    try:
        import json as _json
        from tasks.generate import run_generate

        # 从排期 JSON 里读取生成参数
        c = database.conn()
        row = c.execute("SELECT generate_schedule_json FROM account WHERE id=?", (account_id,)).fetchone()
        c.close()
        sched = {}
        if row and row["generate_schedule_json"]:
            try:
                sched = _json.loads(row["generate_schedule_json"])
            except Exception:
                pass

        _raw_mode = sched.get("image_mode") or "random"
        if _raw_mode == "random":
            import random as _rand
            image_mode = _rand.choice(["cards", "ai", "both"])
        else:
            image_mode = _raw_mode                             # 固定模式
        content_type   = sched.get("content_type") or None     # None = 轮询
        pillar         = sched.get("pillar") or None           # None = AI 自决

        count = run_generate(
            account_id=account_id,
            image_mode=image_mode,
            content_type_override=content_type,
            pillar_override=pillar,
        )
        logger.info(f"[scheduler] account {account_id} 生成完成，新增 {count} 篇")
    except Exception as e:
        logger.error(f"[scheduler] account {account_id} 生成任务异常：{e}", exc_info=True)


def _run_publish_all() -> None:
    try:
        from tasks.publish import run_publish
        c = database.conn()
        accounts = c.execute("SELECT id FROM account").fetchall()
        c.close()
        total = 0
        for acc in accounts:
            total += run_publish(account_id=acc["id"])
        if total:
            logger.info(f"[scheduler] 发布完成，本次共 {total} 篇")
    except Exception as e:
        logger.error(f"[scheduler] 发布任务异常：{e}", exc_info=True)


