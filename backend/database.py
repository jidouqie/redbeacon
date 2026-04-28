import sqlite3
from pathlib import Path

DB_PATH: Path | None = None


def init_db(data_dir: str) -> None:
    """初始化数据库路径，创建所有表。启动时调用一次。"""
    global DB_PATH
    p = Path(data_dir)
    p.mkdir(parents=True, exist_ok=True)
    DB_PATH = p / "redbeacon.db"
    _create_tables()


def conn() -> sqlite3.Connection:
    if DB_PATH is None:
        raise RuntimeError("数据库未初始化，请先调用 init_db()")
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")   # 允许并发读
    c.execute("PRAGMA foreign_keys=ON")
    return c


def _seed_defaults(c: sqlite3.Connection) -> None:
    """写入默认配置行，已存在的 key 不覆盖。"""
    defaults = [
        ("publish_is_original",     "false", 0),
        ("publish_is_ai_generated", "true",  0),
        ("publish_visibility",      "公开可见", 0),
    ]
    for key, value, is_enc in defaults:
        c.execute(
            """INSERT OR IGNORE INTO settings (key, value, is_encrypted, updated_at)
               VALUES (?, ?, ?, datetime('now'))""",
            (key, value, is_enc),
        )
    c.commit()


def _migrate(c: sqlite3.Connection) -> None:
    """添加新列（幂等，忽略已存在错误）。"""
    migrations = [
        ("content_queue", "tags",              "TEXT NOT NULL DEFAULT '[]'"),
        ("content_queue", "image_prompt",      "TEXT"),
        ("content_queue", "content_type",      "TEXT"),
        # 账号级飞书配置（每账号对应一张飞书表格）
        ("account", "display_name",        "TEXT"),
        ("account", "feishu_app_token",    "TEXT"),
        ("account", "feishu_table_id",     "TEXT"),
        ("account", "feishu_user_id",      "TEXT"),
        # MCP 启动模式（1=无头，0=有头显示浏览器）
        ("account", "mcp_headless",            "INTEGER NOT NULL DEFAULT 1"),
        # 账号级自动生成配置
        ("account", "auto_generate_enabled",   "INTEGER NOT NULL DEFAULT 1"),
        ("account", "generate_schedule_json",  "TEXT"),
        # 图片模板选择模式：specific=使用激活模板，random=每次随机选一个
        ("image_strategy", "template_mode",    "TEXT NOT NULL DEFAULT 'specific'"),
    ]
    for table, col, typedef in migrations:
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
            c.commit()
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                import logging as _log
                _log.getLogger("database").warning(f"[migrate] {table}.{col}: {e}")

    # 数据迁移：将全局 settings 中的飞书表格参数迁移到 account 表第一行
    _migrate_feishu_to_account(c)


def _migrate_feishu_to_account(c: sqlite3.Connection) -> None:
    """一次性将 settings 里的 feishu_app_token/table_id/user_id 迁移到 account id=1。"""
    acc = c.execute("SELECT id, feishu_app_token FROM account WHERE id=1").fetchone()
    if acc is None or acc["feishu_app_token"]:
        return  # 没有账号，或已迁移过

    keys = ("feishu_app_token", "feishu_table_id", "feishu_user_id")
    vals: dict[str, str] = {}
    for key in keys:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if row and row["value"]:
            vals[key] = row["value"]

    if not vals:
        return

    sets = ", ".join(f"{k}=?" for k in vals)
    c.execute(f"UPDATE account SET {sets} WHERE id=1", list(vals.values()))
    # 从 settings 删除已迁移的 key（避免歧义）
    for key in vals:
        c.execute("DELETE FROM settings WHERE key=?", (key,))
    c.commit()


def _create_tables() -> None:
    c = conn()
    c.executescript("""
        -- 全局配置（API Key 等加密存储）
        CREATE TABLE IF NOT EXISTS settings (
            key          TEXT PRIMARY KEY,
            value        TEXT NOT NULL DEFAULT '',
            is_encrypted INTEGER NOT NULL DEFAULT 0,
            updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- 小红书账号（免费版只有一条，id=1）
        CREATE TABLE IF NOT EXISTS account (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname          TEXT,
            xhs_user_id       TEXT,
            cookie_file       TEXT,       -- cookie 文件路径（相对 data_dir）
            proxy             TEXT,       -- 可选代理，格式 http://host:port
            mcp_port          INTEGER NOT NULL DEFAULT 18060,
            mcp_pid           INTEGER,    -- 当前 xiaohongshu-mcp 进程 PID
            login_status      TEXT NOT NULL DEFAULT 'unknown',  -- logged_in / logged_out / unknown
            last_login_check  TEXT,
            created_at        TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- 账号策略（来自 Skill 输出的 JSON，带版本号）
        CREATE TABLE IF NOT EXISTS strategy (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id   INTEGER NOT NULL REFERENCES account(id),
            version      INTEGER NOT NULL DEFAULT 1,
            data         TEXT NOT NULL,   -- 完整策略 JSON
            niche        TEXT,            -- 冗余字段，方便查询
            posting_freq TEXT,            -- 冗余字段，方便 scheduler 读取
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- 提示词（文案风格 / 配图风格，各最多 3 条免费版）
        CREATE TABLE IF NOT EXISTS prompt (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id   INTEGER NOT NULL REFERENCES account(id),
            type         TEXT NOT NULL,   -- copy / image
            name         TEXT NOT NULL,   -- 主文案风格 / 主配图风格 / ...
            prompt_text  TEXT NOT NULL,
            notes        TEXT,
            version      INTEGER NOT NULL DEFAULT 1,
            is_active    INTEGER NOT NULL DEFAULT 1,
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- 内容队列（AI 生成 → 待审核 → 已发布）
        CREATE TABLE IF NOT EXISTS content_queue (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id       INTEGER NOT NULL REFERENCES account(id),
            topic            TEXT NOT NULL,
            pillar_name      TEXT,        -- 归属的内容支柱
            title            TEXT,
            body             TEXT,        -- Markdown 正文
            images           TEXT,        -- JSON 数组，图片文件路径列表
            visual_theme     TEXT,        -- 渲染时使用的视觉主题
            prompt_version   INTEGER,     -- 生成时使用的 prompt 版本号
            feishu_record_id TEXT,        -- 飞书多维表格行 ID，用于状态同步
            status           TEXT NOT NULL DEFAULT 'pending_review',
                                          -- pending_review / approved / rejected / published / failed
            review_comment   TEXT,        -- 审核意见（用户填写）
            scheduled_at     TEXT,        -- 计划发布时间
            published_at     TEXT,
            xhs_note_id      TEXT,        -- 发布成功后小红书返回的笔记 ID
            error_msg        TEXT,        -- 发布失败原因
            created_at       TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- 发布历史日志
        CREATE TABLE IF NOT EXISTS publish_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id   INTEGER NOT NULL REFERENCES content_queue(id),
            account_id   INTEGER NOT NULL REFERENCES account(id),
            xhs_note_id  TEXT,
            status       TEXT NOT NULL,   -- success / failed
            error_msg    TEXT,
            published_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- 内容类型（干货/获客/故事/痛点解析等，每种有独立提示词模板）
        CREATE TABLE IF NOT EXISTS content_type (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id       INTEGER NOT NULL REFERENCES account(id),
            name             TEXT NOT NULL,
            prompt_template  TEXT NOT NULL DEFAULT '',
            is_active        INTEGER NOT NULL DEFAULT 1,
            sort_order       INTEGER NOT NULL DEFAULT 0,
            created_at       TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- 选题库（用户管理的选题/痛点问题，生成时原子消费）
        CREATE TABLE IF NOT EXISTS topic (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id   INTEGER NOT NULL REFERENCES account(id),
            content_type TEXT NOT NULL DEFAULT '干货',
            content      TEXT NOT NULL,
            is_used      INTEGER NOT NULL DEFAULT 0,
            used_at      TEXT,
            created_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- 图片策略（每账号一行，多种生成模式配置）
        CREATE TABLE IF NOT EXISTS image_strategy (
            account_id       INTEGER PRIMARY KEY REFERENCES account(id),
            mode             TEXT NOT NULL DEFAULT 'cards',
            prompt_template  TEXT NOT NULL DEFAULT '',
            card_theme       TEXT NOT NULL DEFAULT 'default',
            reference_images TEXT NOT NULL DEFAULT '[]',
            ai_model         TEXT,
            updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- AI 图片提示词模板（每账号多套，每套含多个 item）
        CREATE TABLE IF NOT EXISTS image_template (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id  INTEGER NOT NULL REFERENCES account(id),
            name        TEXT NOT NULL,
            is_active   INTEGER NOT NULL DEFAULT 0,
            items       TEXT NOT NULL DEFAULT '[]',
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    c.commit()

    # ── 写入默认配置（已存在的 key 不覆盖）────────────────────────────────────────
    _seed_defaults(c)

    # ── 渐进迁移：为旧表补充新字段 ───────────────────────────────────────────────
    _migrate(c)
    c.close()
