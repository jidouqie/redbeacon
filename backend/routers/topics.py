"""
选题库 & 内容类型管理。

路由结构（均挂载在 /api/topics/{account_id} 下）：

  内容类型（content_type）：
    GET    /types                    ← 列出所有类型
    POST   /types                    ← 新建类型
    PUT    /types/{type_id}          ← 更新名称 / 提示词模板 / 激活状态
    DELETE /types/{type_id}          ← 删除类型

  选题（topic）：
    GET    /                         ← 列出选题（可按 content_type / is_used 筛选）
    POST   /                         ← 新建单条选题
    POST   /batch                    ← 批量导入（换行分隔文本）
    DELETE /{topic_id}               ← 删除选题
    POST   /{topic_id}/reset         ← 标记为未使用
    POST   /reset-all                ← 重置全部已用选题
    GET    /stats                    ← 统计信息
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import database
from utils.logger import get_logger

router = APIRouter()
logger = get_logger("router.topics")

# ── 默认提示词模板 ────────────────────────────────────────────────────────────

DEFAULT_PROMPT = """\
你是一个专注于{niche}领域的小红书博主。

目标受众：{target_audience}
语气风格：{tone}
开场方式：{opening_style}
行文格式：{format_style}
Emoji 用量：{emoji_usage}
正文字数：{content_length}
内容方向：{content_pillars}
差异化优势：{competitive_advantage}
目标痛点：{pain_points}
禁止词汇：{forbidden_words}
本次内容类型：{content_type}

请以【{topic}】为主题，创作一篇小红书笔记。

创作要求：
1. 标题：不超过20字，有吸引力，可加数字或疑问句形式
2. 正文：严格遵守上方字数、语气、格式等要求
3. 标签：9个相关话题标签（如 #职场干货 的格式）

禁止：正文中不要出现"关注/点赞/收藏"等引导词，不要出现广告推销语。

严格按以下 JSON 格式输出，不要有任何额外文字：
```json
{
  "title": "标题",
  "content": "正文",
  "tags": ["#标签1", "#标签2", "#标签3", "#标签4", "#标签5", "#标签6", "#标签7", "#标签8", "#标签9"]
}
```"""

# 默认内容类型（首次为账号创建类型时预填）
DEFAULT_TYPES = [
    ("干货科普", DEFAULT_PROMPT),
    ("痛点解析", DEFAULT_PROMPT.replace("本次内容类型：{content_type}", "本次内容类型：痛点解析\n聚焦用户痛点，先戳痛点再给解法，引发共鸣")),
    ("经验分享", DEFAULT_PROMPT.replace("本次内容类型：{content_type}", "本次内容类型：经验分享\n以第一人称讲述真实经历，故事化表达，真实感强")),
]


# ── Schema ────────────────────────────────────────────────────────────────────

class ContentTypeOut(BaseModel):
    id: int
    name: str
    prompt_template: str
    is_active: bool
    sort_order: int


class ContentTypeIn(BaseModel):
    name: str
    prompt_template: str = DEFAULT_PROMPT
    sort_order: int = 0


class ContentTypeUpdate(BaseModel):
    name: str | None = None
    prompt_template: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class TopicOut(BaseModel):
    id: int
    content_type: str
    content: str
    is_used: bool
    used_at: str | None
    created_at: str


class TopicIn(BaseModel):
    content_type: str
    content: str


class BatchImport(BaseModel):
    content_type: str
    text: str   # 换行分隔的选题列表


class StatsOut(BaseModel):
    total: int
    unused: int
    used: int
    by_type: list[dict]


# ── 内容类型路由 ───────────────────────────────────────────────────────────────

@router.get("/{account_id}/types", response_model=list[ContentTypeOut])
def list_content_types(account_id: int):
    c = database.conn()
    rows = c.execute(
        "SELECT * FROM content_type WHERE account_id=? ORDER BY sort_order, id",
        (account_id,),
    ).fetchall()
    c.close()
    # 若从未创建过，返回默认类型（不入库，让前端触发初始化）
    return [_ct_row_to_out(r) for r in rows]


@router.post("/{account_id}/types", response_model=ContentTypeOut, status_code=201)
def create_content_type(account_id: int, body: ContentTypeIn):
    _require_account(account_id)
    now = datetime.now(timezone.utc).isoformat()
    c = database.conn()
    c.execute(
        """INSERT INTO content_type (account_id, name, prompt_template, sort_order, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (account_id, body.name, body.prompt_template, body.sort_order, now, now),
    )
    c.commit()
    row = c.execute("SELECT * FROM content_type WHERE rowid=last_insert_rowid()").fetchone()
    c.close()
    return _ct_row_to_out(row)


@router.post("/{account_id}/types/init", response_model=list[ContentTypeOut])
def init_default_types(account_id: int):
    """若账号尚无任何内容类型，插入默认三套。"""
    _require_account(account_id)
    c = database.conn()
    count = c.execute("SELECT COUNT(*) FROM content_type WHERE account_id=?", (account_id,)).fetchone()[0]
    if count > 0:
        rows = c.execute("SELECT * FROM content_type WHERE account_id=? ORDER BY sort_order", (account_id,)).fetchall()
        c.close()
        return [_ct_row_to_out(r) for r in rows]

    now = datetime.now(timezone.utc).isoformat()
    for i, (name, tmpl) in enumerate(DEFAULT_TYPES):
        c.execute(
            """INSERT INTO content_type (account_id, name, prompt_template, sort_order, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (account_id, name, tmpl, i, now, now),
        )
    c.commit()
    rows = c.execute("SELECT * FROM content_type WHERE account_id=? ORDER BY sort_order", (account_id,)).fetchall()
    c.close()
    return [_ct_row_to_out(r) for r in rows]


@router.put("/{account_id}/types/{type_id}", response_model=ContentTypeOut)
def update_content_type(account_id: int, type_id: int, body: ContentTypeUpdate):
    c = database.conn()
    row = c.execute(
        "SELECT * FROM content_type WHERE id=? AND account_id=?", (type_id, account_id)
    ).fetchone()
    if row is None:
        c.close()
        raise HTTPException(404, "内容类型不存在")
    now = datetime.now(timezone.utc).isoformat()
    updates: dict = {}
    if body.name is not None:         updates["name"] = body.name
    if body.prompt_template is not None: updates["prompt_template"] = body.prompt_template
    if body.is_active is not None:    updates["is_active"] = int(body.is_active)
    if body.sort_order is not None:   updates["sort_order"] = body.sort_order
    if updates:
        sets = ", ".join(f"{k}=?" for k in updates)
        vals = list(updates.values()) + [now, type_id, account_id]
        c.execute(f"UPDATE content_type SET {sets}, updated_at=? WHERE id=? AND account_id=?", vals)
        c.commit()
    row = c.execute("SELECT * FROM content_type WHERE id=?", (type_id,)).fetchone()
    c.close()
    return _ct_row_to_out(row)


@router.delete("/{account_id}/types/{type_id}", status_code=204)
def delete_content_type(account_id: int, type_id: int):
    c = database.conn()
    c.execute("DELETE FROM content_type WHERE id=? AND account_id=?", (type_id, account_id))
    c.commit()
    c.close()


# ── 选题路由 ───────────────────────────────────────────────────────────────────

@router.get("/{account_id}/stats", response_model=StatsOut)
def get_stats(account_id: int):
    c = database.conn()
    total = c.execute("SELECT COUNT(*) FROM topic WHERE account_id=?", (account_id,)).fetchone()[0]
    unused = c.execute("SELECT COUNT(*) FROM topic WHERE account_id=? AND is_used=0", (account_id,)).fetchone()[0]
    by_type_rows = c.execute(
        """SELECT content_type,
                  COUNT(*) as total,
                  SUM(CASE WHEN is_used=0 THEN 1 ELSE 0 END) as unused
           FROM topic WHERE account_id=? GROUP BY content_type""",
        (account_id,),
    ).fetchall()
    c.close()
    return StatsOut(
        total=total,
        unused=unused,
        used=total - unused,
        by_type=[{"content_type": r["content_type"], "total": r["total"], "unused": r["unused"]} for r in by_type_rows],
    )


@router.get("/{account_id}", response_model=list[TopicOut])
def list_topics(
    account_id: int,
    content_type: str | None = None,
    is_used: int | None = None,
    limit: int = 100,
    offset: int = 0,
):
    c = database.conn()
    wheres = ["account_id=?"]
    params: list = [account_id]
    if content_type:
        wheres.append("content_type=?")
        params.append(content_type)
    if is_used is not None:
        wheres.append("is_used=?")
        params.append(is_used)
    where_sql = " AND ".join(wheres)
    rows = c.execute(
        f"SELECT * FROM topic WHERE {where_sql} ORDER BY is_used, id DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    c.close()
    return [_topic_row_to_out(r) for r in rows]


@router.post("/{account_id}", response_model=TopicOut, status_code=201)
def create_topic(account_id: int, body: TopicIn):
    _require_account(account_id)
    now = datetime.now(timezone.utc).isoformat()
    c = database.conn()
    c.execute(
        "INSERT INTO topic (account_id, content_type, content, created_at) VALUES (?, ?, ?, ?)",
        (account_id, body.content_type, body.content.strip(), now),
    )
    c.commit()
    row = c.execute("SELECT * FROM topic WHERE rowid=last_insert_rowid()").fetchone()
    c.close()
    return _topic_row_to_out(row)


@router.post("/{account_id}/batch", status_code=201)
def batch_import_topics(account_id: int, body: BatchImport):
    """批量导入选题（换行分隔），去除空行和重复。返回实际插入数。"""
    _require_account(account_id)
    lines = [l.strip() for l in body.text.splitlines() if l.strip()]
    if not lines:
        return {"inserted": 0}
    now = datetime.now(timezone.utc).isoformat()
    c = database.conn()
    inserted = 0
    for line in lines:
        # 简单去重：同 account + content_type + content 已存在则跳过
        exists = c.execute(
            "SELECT id FROM topic WHERE account_id=? AND content_type=? AND content=?",
            (account_id, body.content_type, line),
        ).fetchone()
        if not exists:
            c.execute(
                "INSERT INTO topic (account_id, content_type, content, created_at) VALUES (?, ?, ?, ?)",
                (account_id, body.content_type, line, now),
            )
            inserted += 1
    c.commit()
    c.close()
    logger.info(f"[topics] account {account_id} 批量导入 {inserted}/{len(lines)} 条选题（类型：{body.content_type}）")
    return {"inserted": inserted, "total": len(lines)}


@router.delete("/{account_id}/{topic_id}", status_code=204)
def delete_topic(account_id: int, topic_id: int):
    c = database.conn()
    c.execute("DELETE FROM topic WHERE id=? AND account_id=?", (topic_id, account_id))
    c.commit()
    c.close()


@router.post("/{account_id}/{topic_id}/reset")
def reset_topic(account_id: int, topic_id: int):
    c = database.conn()
    c.execute(
        "UPDATE topic SET is_used=0, used_at=NULL WHERE id=? AND account_id=?",
        (topic_id, account_id),
    )
    c.commit()
    c.close()
    return {"ok": True}


@router.post("/{account_id}/reset-all")
def reset_all_topics(account_id: int, content_type: str | None = None):
    c = database.conn()
    if content_type:
        c.execute(
            "UPDATE topic SET is_used=0, used_at=NULL WHERE account_id=? AND content_type=?",
            (account_id, content_type),
        )
    else:
        c.execute("UPDATE topic SET is_used=0, used_at=NULL WHERE account_id=?", (account_id,))
    c.commit()
    c.close()
    return {"ok": True}


# ── AI 灵感生成选题 ─────────────────────────────────────────────────────────────

class InspireIn(BaseModel):
    text: str  # 用户输入的灵感文字


@router.post("/{account_id}/inspire")
def inspire_topics(account_id: int, body: InspireIn):
    """
    用户输入一段灵感文字，AI 提炼并生成 5 条具体选题选项，供用户勾选后加入选题库。
    """
    import httpx
    from openai import OpenAI
    import config as cfg

    api_key  = cfg.get("ai_api_key")
    base_url = cfg.get("ai_base_url", "https://api.openai.com/v1")
    model    = cfg.get("ai_model", "gpt-4o-mini")
    if not api_key:
        raise HTTPException(400, "AI API Key 未配置")

    # 读取账号定位作为上下文
    c = database.conn()
    strategy_row = c.execute(
        "SELECT data FROM strategy WHERE account_id=? ORDER BY version DESC LIMIT 1",
        (account_id,),
    ).fetchone()
    c.close()

    niche = "通用"
    if strategy_row:
        import json as _json
        try:
            d = _json.loads(strategy_row["data"])
            niche = d.get("niche", "通用")
        except Exception:
            pass

    prompt = f"""你是一个{niche}领域的小红书内容策划专家。

用户有以下灵感：
"{body.text}"

请基于这个灵感，生成5个具体的小红书笔记选题标题。

要求：
- 每条选题都是完整的笔记标题，不超过25字
- 有吸引力，适合小红书风格（口语化、有共鸣、可加数字）
- 与"{niche}"领域相关
- 5条选题要有差异性，覆盖不同角度

只输出5条标题，每行一条，不要编号，不要任何额外说明。"""

    try:
        client = OpenAI(
            api_key=api_key, base_url=base_url,
            http_client=httpx.Client(trust_env=False, timeout=30),
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=500,
        )
        raw = resp.choices[0].message.content.strip()
        options = [line.strip() for line in raw.splitlines() if line.strip()][:6]
        return {"options": options}
    except Exception as e:
        raise HTTPException(502, f"AI 生成失败：{e}")


# ── 工具 ──────────────────────────────────────────────────────────────────────

def _require_account(account_id: int) -> None:
    c = database.conn()
    exists = c.execute("SELECT id FROM account WHERE id=?", (account_id,)).fetchone()
    c.close()
    if not exists:
        raise HTTPException(404, f"账号 {account_id} 不存在")


def _ct_row_to_out(row) -> ContentTypeOut:
    return ContentTypeOut(
        id=row["id"],
        name=row["name"],
        prompt_template=row["prompt_template"],
        is_active=bool(row["is_active"]),
        sort_order=row["sort_order"],
    )


def _topic_row_to_out(row) -> TopicOut:
    return TopicOut(
        id=row["id"],
        content_type=row["content_type"],
        content=row["content"],
        is_used=bool(row["is_used"]),
        used_at=row["used_at"],
        created_at=row["created_at"],
    )


def pop_next_topic(account_id: int, content_type: str | None = None) -> dict | None:
    """
    原子消费一条未使用选题（先进先出）。
    返回选题 dict，若无可用选题返回 None。
    供 tasks/generate.py 调用。
    """
    now = datetime.now(timezone.utc).isoformat()
    c = database.conn()
    try:
        # BEGIN IMMEDIATE 立即获取写锁，防止并发重复消费同一条选题
        c.execute("BEGIN IMMEDIATE")
        if content_type:
            row = c.execute(
                "SELECT * FROM topic WHERE account_id=? AND content_type=? AND is_used=0 ORDER BY id LIMIT 1",
                (account_id, content_type),
            ).fetchone()
        else:
            row = c.execute(
                "SELECT * FROM topic WHERE account_id=? AND is_used=0 ORDER BY id LIMIT 1",
                (account_id,),
            ).fetchone()
        if row is None:
            c.execute("ROLLBACK")
            return None
        c.execute(
            "UPDATE topic SET is_used=1, used_at=? WHERE id=?",
            (now, row["id"]),
        )
        c.commit()
        return dict(row)
    except Exception:
        c.execute("ROLLBACK")
        raise
    finally:
        c.close()
