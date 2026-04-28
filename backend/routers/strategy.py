"""账号策略：Skill 输出的 JSON 写入与读取。路由全部以 account_id 参数化。"""
import base64
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config as cfg
from fastapi import APIRouter, Body, HTTPException, UploadFile, File
from pydantic import BaseModel

import database
from utils.logger import get_logger

router = APIRouter()
logger = get_logger("router.strategy")

FREE_PROMPT_LIMIT = 3


# ── Schema ─────────────────────────────────────────────────────────────────────

class StrategyIn(BaseModel):
    data: dict




class ImageStrategyIn(BaseModel):
    mode: str = "cards"
    prompt_template: str = ""
    card_theme: str = "default"
    reference_images: list[str] = []
    ai_model: str | None = None
    template_mode: str = "specific"  # "specific" | "random"


class PromptIn(BaseModel):
    type: str
    name: str
    prompt_text: str
    notes: str | None = None


class PromptOut(BaseModel):
    id: int
    type: str
    name: str
    prompt_text: str
    notes: str | None
    version: int
    is_active: bool


class PromptUpdate(BaseModel):
    prompt_text: str
    notes: str | None = None


class ImageTemplateItem(BaseModel):
    image_path: str = ""   # 本地绝对路径 或 data:image/... base64 或空字符串
    prompt: str = ""


class ImageTemplateIn(BaseModel):
    name: str
    items: list[ImageTemplateItem] = []


class ImageTemplateOut(BaseModel):
    id: int
    account_id: int
    name: str
    is_active: bool
    items: list[ImageTemplateItem]
    created_at: str
    updated_at: str


# ── 策略路由 ───────────────────────────────────────────────────────────────────

@router.get("/{account_id}")
def get_strategy(account_id: int):
    c = database.conn()
    row = c.execute(
        "SELECT * FROM strategy WHERE account_id=? ORDER BY version DESC LIMIT 1",
        (account_id,),
    ).fetchone()
    c.close()
    return dict(row) if row else None


@router.post("/{account_id}")
def upsert_strategy(account_id: int, body: StrategyIn):
    """写入策略 JSON，自动递增版本号，同步提示词。"""
    _require_account(account_id)
    data = body.data
    niche = data.get("niche", "")
    posting_freq = data.get("posting_frequency", "")
    now = datetime.now(timezone.utc).isoformat()

    c = database.conn()
    last = c.execute(
        "SELECT version FROM strategy WHERE account_id=? ORDER BY version DESC LIMIT 1",
        (account_id,),
    ).fetchone()
    new_version = (last["version"] + 1) if last else 1

    c.execute(
        """INSERT INTO strategy (account_id, version, data, niche, posting_freq, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (account_id, new_version, json.dumps(data, ensure_ascii=False), niche, posting_freq, now, now),
    )
    c.commit()
    c.close()

    _sync_prompts_from_strategy(account_id, data)
    _ensure_content_types(account_id)
    logger.info(f"策略已更新 account={account_id} v{new_version} niche={niche}")
    return {"version": new_version}


@router.patch("/{account_id}")
def edit_strategy(account_id: int, fields: dict[str, Any] = Body(...)):
    """就地将传入的任意字段合并到最新版策略，不新增版本号。"""
    _require_account(account_id)
    c = database.conn()
    row = c.execute(
        "SELECT id, data FROM strategy WHERE account_id=? ORDER BY version DESC LIMIT 1",
        (account_id,),
    ).fetchone()

    if row is None:
        data: dict = {}
    else:
        try:
            data = json.loads(row["data"])
        except Exception:
            data = {}

    data.update(fields)

    now = datetime.now(timezone.utc).isoformat()
    if row is None:
        c.execute(
            """INSERT INTO strategy (account_id, version, data, niche, posting_freq, created_at, updated_at)
               VALUES (?, 1, ?, ?, ?, ?, ?)""",
            (account_id, json.dumps(data, ensure_ascii=False),
             data.get("niche", ""), data.get("posting_frequency", ""), now, now),
        )
    else:
        c.execute(
            """UPDATE strategy SET data=?, niche=?, posting_freq=?, updated_at=? WHERE id=?""",
            (json.dumps(data, ensure_ascii=False),
             data.get("niche", ""), data.get("posting_frequency", ""),
             now, row["id"]),
        )
    c.commit()
    c.close()
    _ensure_content_types(account_id)
    logger.info(f"策略已就地更新 account={account_id} fields={list(fields.keys())}")
    return {"ok": True}


def _ensure_content_types(account_id: int) -> None:
    """如果账号尚无内容类型，自动初始化默认三类。幂等，已有则跳过。"""
    from routers.topics import init_default_types
    init_default_types(account_id)


def _sync_prompts_from_strategy(account_id: int, data: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    c = database.conn()
    for ptype, key in [("copy", "copy_style_prompts"), ("image", "image_style_prompts")]:
        for p in data.get(key, []):
            name = p.get("name", f"主{ptype}风格")
            text = p.get("prompt", "")
            notes = p.get("notes", "")
            existing = c.execute(
                "SELECT id FROM prompt WHERE account_id=? AND type=? AND name=?",
                (account_id, ptype, name),
            ).fetchone()
            if not existing:
                c.execute(
                    """INSERT INTO prompt (account_id, type, name, prompt_text, notes, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (account_id, ptype, name, text, notes, now, now),
                )
    c.commit()
    c.close()


# ── 提示词路由 ─────────────────────────────────────────────────────────────────

@router.get("/{account_id}/prompts", response_model=list[PromptOut])
def list_prompts(account_id: int, type: str | None = None):
    c = database.conn()
    if type:
        rows = c.execute(
            "SELECT * FROM prompt WHERE account_id=? AND type=? ORDER BY id",
            (account_id, type),
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT * FROM prompt WHERE account_id=? ORDER BY type, id",
            (account_id,),
        ).fetchall()
    c.close()
    return [PromptOut(**dict(r)) for r in rows]


@router.post("/{account_id}/prompts", response_model=PromptOut)
def add_prompt(account_id: int, body: PromptIn):
    _require_account(account_id)
    c = database.conn()
    count = c.execute(
        "SELECT COUNT(*) FROM prompt WHERE account_id=? AND type=? AND is_active=1",
        (account_id, body.type),
    ).fetchone()[0]
    if count >= FREE_PROMPT_LIMIT:
        c.close()
        raise HTTPException(
            403,
            f"当前账号 {body.type} 类型提示词已有 {count} 套，上限 {FREE_PROMPT_LIMIT} 套"
        )
    now = datetime.now(timezone.utc).isoformat()
    c.execute(
        """INSERT INTO prompt (account_id, type, name, prompt_text, notes, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (account_id, body.type, body.name, body.prompt_text, body.notes, now, now),
    )
    c.commit()
    row = c.execute("SELECT * FROM prompt WHERE rowid=last_insert_rowid()").fetchone()
    c.close()
    return PromptOut(**dict(row))


@router.put("/{account_id}/prompts/{prompt_id}", response_model=PromptOut)
def update_prompt(account_id: int, prompt_id: int, body: PromptUpdate):
    now = datetime.now(timezone.utc).isoformat()
    c = database.conn()
    c.execute(
        """UPDATE prompt SET prompt_text=?, notes=?, version=version+1, updated_at=?
           WHERE id=? AND account_id=?""",
        (body.prompt_text, body.notes, now, prompt_id, account_id),
    )
    c.commit()
    row = c.execute("SELECT * FROM prompt WHERE id=?", (prompt_id,)).fetchone()
    c.close()
    if row is None:
        raise HTTPException(404, "提示词不存在")
    return PromptOut(**dict(row))


# ── 图片策略 ───────────────────────────────────────────────────────────────────

_IMG_STRATEGY_DEFAULT_PROMPT = (
    "小红书封面图，{niche}领域，主题：{title}，"
    "色彩明亮，竖版3:4比例，小红书风格，高质量精美"
)


@router.get("/{account_id}/image")
def get_image_strategy(account_id: int):
    c = database.conn()
    row = c.execute(
        "SELECT * FROM image_strategy WHERE account_id=?", (account_id,)
    ).fetchone()
    c.close()
    if row is None:
        return {
            "mode": "cards",
            "prompt_template": _IMG_STRATEGY_DEFAULT_PROMPT,
            "card_theme": "default",
            "reference_images": [],
            "ai_model": None,
            "template_mode": "specific",
        }
    return {
        "mode": row["mode"],
        "prompt_template": row["prompt_template"],
        "card_theme": row["card_theme"],
        "reference_images": json.loads(row["reference_images"] or "[]"),
        "ai_model": row["ai_model"],
        "template_mode": row["template_mode"] if "template_mode" in row.keys() else "specific",
    }


@router.put("/{account_id}/image")
def upsert_image_strategy(account_id: int, body: ImageStrategyIn):
    _require_account(account_id)
    now = datetime.now(timezone.utc).isoformat()
    c = database.conn()
    c.execute(
        """INSERT INTO image_strategy
               (account_id, mode, prompt_template, card_theme, reference_images, ai_model, template_mode, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(account_id) DO UPDATE SET
               mode=excluded.mode,
               prompt_template=excluded.prompt_template,
               card_theme=excluded.card_theme,
               reference_images=excluded.reference_images,
               ai_model=excluded.ai_model,
               template_mode=excluded.template_mode,
               updated_at=excluded.updated_at""",
        (account_id, body.mode, body.prompt_template, body.card_theme,
         json.dumps(body.reference_images, ensure_ascii=False),
         body.ai_model, body.template_mode, now),
    )
    c.commit()
    c.close()
    return {"ok": True}


# ── 图片模板路由 ────────────────────────────────────────────────────────────────

@router.get("/{account_id}/image-templates", response_model=list[ImageTemplateOut])
def list_image_templates(account_id: int):
    c = database.conn()
    rows = c.execute(
        "SELECT * FROM image_template WHERE account_id=? ORDER BY id",
        (account_id,),
    ).fetchall()
    c.close()
    return [_row_to_template(r) for r in rows]


@router.post("/{account_id}/image-templates", response_model=ImageTemplateOut)
def create_image_template(account_id: int, body: ImageTemplateIn):
    _require_account(account_id)
    now = datetime.now(timezone.utc).isoformat()
    c = database.conn()
    c.execute(
        """INSERT INTO image_template (account_id, name, is_active, items, created_at, updated_at)
           VALUES (?, ?, 0, ?, ?, ?)""",
        (account_id, body.name, json.dumps([i.dict() for i in body.items], ensure_ascii=False), now, now),
    )
    c.commit()
    row = c.execute("SELECT * FROM image_template WHERE rowid=last_insert_rowid()").fetchone()
    c.close()
    return _row_to_template(row)


@router.put("/{account_id}/image-templates/{template_id}", response_model=ImageTemplateOut)
def update_image_template(account_id: int, template_id: int, body: ImageTemplateIn):
    _require_account(account_id)
    now = datetime.now(timezone.utc).isoformat()
    c = database.conn()
    c.execute(
        """UPDATE image_template SET name=?, items=?, updated_at=?
           WHERE id=? AND account_id=?""",
        (body.name, json.dumps([i.dict() for i in body.items], ensure_ascii=False), now,
         template_id, account_id),
    )
    c.commit()
    row = c.execute("SELECT * FROM image_template WHERE id=? AND account_id=?",
                    (template_id, account_id)).fetchone()
    c.close()
    if row is None:
        raise HTTPException(404, "模板不存在")
    return _row_to_template(row)


@router.delete("/{account_id}/image-templates/{template_id}")
def delete_image_template(account_id: int, template_id: int):
    c = database.conn()
    c.execute("DELETE FROM image_template WHERE id=? AND account_id=?", (template_id, account_id))
    c.commit()
    c.close()
    return {"ok": True}


@router.post("/{account_id}/image-templates/{template_id}/activate")
def activate_image_template(account_id: int, template_id: int):
    c = database.conn()
    c.execute("UPDATE image_template SET is_active=0 WHERE account_id=?", (account_id,))
    c.execute("UPDATE image_template SET is_active=1 WHERE id=? AND account_id=?",
              (template_id, account_id))
    c.commit()
    c.close()
    return {"ok": True}


@router.post("/{account_id}/image-templates/deactivate")
def deactivate_all_templates(account_id: int):
    """取消激活（恢复使用 image_strategy 的 prompt_template）。"""
    c = database.conn()
    c.execute("UPDATE image_template SET is_active=0 WHERE account_id=?", (account_id,))
    c.commit()
    c.close()
    return {"ok": True}


# ── 参考图片上传 ────────────────────────────────────────────────────────────────

@router.post("/{account_id}/upload-image")
async def upload_reference_image(account_id: int, file: UploadFile = File(...)):
    """上传参考图片，保存到 data/images/refs/，返回本地绝对路径。"""
    import os
    data_dir = os.environ.get("REDBEACON_DATA_DIR") or cfg.get("data_dir", "data")
    save_dir = Path(data_dir).resolve() / "images" / "refs"
    save_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename or "image.jpg").suffix or ".jpg"
    filename = f"ref_{int(time.time() * 1000)}{ext}"
    dest = save_dir / filename
    content = await file.read()
    dest.write_bytes(content)

    # 返回相对于 data_dir 的路径，避免绝对路径在迁移后失效
    rel_path = str(Path("images") / "refs" / filename)
    return {"path": rel_path, "filename": filename}


# ── 工具 ───────────────────────────────────────────────────────────────────────

def _row_to_template(row) -> ImageTemplateOut:
    items_raw = json.loads(row["items"] or "[]")
    return ImageTemplateOut(
        id=row["id"],
        account_id=row["account_id"],
        name=row["name"],
        is_active=bool(row["is_active"]),
        items=[ImageTemplateItem(**i) for i in items_raw],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _require_account(account_id: int) -> None:
    c = database.conn()
    exists = c.execute("SELECT id FROM account WHERE id=?", (account_id,)).fetchone()
    c.close()
    if not exists:
        raise HTTPException(404, f"账号 {account_id} 不存在")
