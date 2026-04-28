"""
调试接口：在沙盒中测试文案提示词和图片提示词，不写入数据库，不推送飞书。
"""
import json
import tempfile
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import config as cfg
import database
from utils.logger import get_logger

router = APIRouter()
logger = get_logger("router.debug")


class DebugCopyRequest(BaseModel):
    account_id: int = 1
    topic: str
    content_type: str = ""
    prompt_template: str


class DebugImageRequest(BaseModel):
    account_id: int = 1
    title: str
    prompt: str
    image_path: str = ""   # 参考图本地路径（可为空）
    model: str | None = None


# ── 文案调试 ────────────────────────────────────────────────────────────────────

@router.post("/copy")
def debug_copy(body: DebugCopyRequest):
    """
    用指定提示词模板和话题调用 AI 生成文案，直接返回结果，不入库不推飞书。
    """
    from openai import OpenAI

    api_key  = cfg.get("ai_api_key")
    base_url = cfg.get("ai_base_url", "https://api.openai.com/v1")
    model    = cfg.get("ai_model", "gpt-4o-mini")

    if not api_key:
        raise HTTPException(400, "AI API Key 未配置")

    # 读取账号策略，用于变量替换
    c = database.conn()
    strategy_row = c.execute(
        "SELECT data FROM strategy WHERE account_id=? ORDER BY version DESC LIMIT 1",
        (body.account_id,),
    ).fetchone()
    c.close()

    strategy: dict = {}
    if strategy_row:
        try:
            strategy = json.loads(strategy_row["data"])
        except Exception:
            pass

    pain_points = strategy.get("pain_points", [])
    forbidden   = strategy.get("forbidden_words", [])
    pillars     = strategy.get("content_pillars", [])
    pillar_val  = "、".join(
        p["name"] + (f"（{p['description']}）" if p.get("description") else "")
        for p in pillars if p.get("name")
    )

    filled = (
        body.prompt_template
        .replace("{niche}",                strategy.get("niche", "通用"))
        .replace("{target_audience}",      strategy.get("target_audience", "普通用户"))
        .replace("{content_type}",         body.content_type or "（调试模式）")
        .replace("{topic}",                body.topic)
        .replace("{tone}",                 strategy.get("tone", ""))
        .replace("{competitive_advantage}", strategy.get("competitive_advantage", ""))
        .replace("{opening_style}",        strategy.get("opening_style", ""))
        .replace("{format_style}",         strategy.get("format_style", ""))
        .replace("{emoji_usage}",          strategy.get("emoji_usage", ""))
        .replace("{content_length}",       strategy.get("content_length", ""))
        .replace("{pain_points}",          " / ".join(pain_points))
        .replace("{forbidden_words}",      " ".join(forbidden))
        .replace("{content_pillars}",      pillar_val)
    )

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        http_client=httpx.Client(trust_env=False, timeout=60),
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是小红书文案专家。输出格式：严格合法的JSON对象。"
                        "JSON字符串值内部禁止使用英文双引号，如需引用使用「」替代。"
                    ),
                },
                {"role": "user", "content": filled},
            ],
            temperature=0.85,
            max_tokens=1500,
        )
        raw = response.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(500, f"AI 调用失败：{e}")

    # 复用 generate.py 的 JSON 解析
    from tasks.generate import _parse_json_output
    result = _parse_json_output(raw)

    return {
        "title":        result.get("title", ""),
        "body":         result.get("content", ""),
        "tags":         result.get("tags", []),
        "filled_prompt": filled,
    }


# ── 图片调试 ────────────────────────────────────────────────────────────────────

@router.post("/image")
def debug_image(body: DebugImageRequest):
    """
    用指定提示词和可选参考图调用 AI 生图，返回图片 URL（存 data/debug/ 目录），不入库。
    """
    import os

    api_key  = cfg.get("ai_api_key")
    base_url = cfg.get("ai_base_url", "https://api.openai.com/v1")
    model    = body.model or cfg.get("image_model")

    if not api_key:
        raise HTTPException(400, "AI API Key 未配置")
    if not model:
        raise HTTPException(400, "图片模型未配置，请在设置中填写图片模型")

    # 读取账号策略，用于 {niche} 替换
    c = database.conn()
    strategy_row = c.execute(
        "SELECT data FROM strategy WHERE account_id=? ORDER BY version DESC LIMIT 1",
        (body.account_id,),
    ).fetchone()
    c.close()

    strategy: dict = {}
    if strategy_row:
        try:
            strategy = json.loads(strategy_row["data"])
        except Exception:
            pass

    effective_prompt = (
        body.prompt
        .replace("{niche}", strategy.get("niche", ""))
        .replace("{title}", body.title)
    )

    # 存 debug 专属目录，不入内容队列
    data_dir = os.environ.get("REDBEACON_DATA_DIR") or cfg.get("data_dir", "data")
    save_dir = str(Path(data_dir).resolve() / "debug_images")
    Path(save_dir).mkdir(parents=True, exist_ok=True)

    reference_items = None
    if body.image_path:
        # 统一解析成绝对路径，避免 image_gen 内部 data_dir 拼接不一致导致找不到文件
        ref_path = Path(body.image_path)
        if not ref_path.is_absolute():
            ref_path = (Path(data_dir).resolve() / ref_path).resolve()
        reference_items = [{"image_path": str(ref_path), "prompt": effective_prompt}]

    try:
        from services.image_gen import generate as gen_image
        paths = gen_image(
            effective_prompt,
            save_dir,
            model=model,
            count=1,
            reference_items=reference_items,
        )
    except Exception as e:
        raise HTTPException(500, f"图片生成失败：{e}")

    if not paths:
        raise HTTPException(500, "AI 未返回图片，请检查模型配置或提示词")

    # 返回可供前端访问的 URL（复用内容图片代理路由）
    rel = Path(paths[0]).name
    debug_dir_name = "debug_images"
    image_url = f"/api/content/{body.account_id}/image?path={debug_dir_name}/{rel}"

    return {
        "image_url":       image_url,
        "image_path":      paths[0],
        "effective_prompt": effective_prompt,
    }
