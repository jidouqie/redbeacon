"""
内容生成任务：从选题库取题 → AI 生成 JSON 文案 → AI 生成图片 → 写入内容队列。

调用入口：
  - APScheduler 定时触发：run_generate()
  - API 手动触发：run_generate()
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import database
import config as cfg
from utils.logger import get_logger

logger = get_logger("tasks.generate")

# ── 渲染器路径 ─────────────────────────────────────────────────────────────────
# frozen（生产）：使用同目录的 RedBeaconRenderer 二进制
# 开发：使用 backend/render_xhs_v2.py（通过系统 Python 调用）
if os.environ.get("REDBEACON_RENDERER"):
    _RENDERER = Path(os.environ["REDBEACON_RENDERER"])
elif getattr(sys, "frozen", False):
    _RENDERER = Path(sys.executable).parent / "RedBeaconRenderer"
else:
    _RENDERER = Path(__file__).parent.parent / "render_xhs_v2.py"

_THEME_MAP = {
    "default":           "elegant",
    "neo-brutalism":     "dark",
    "botanical":         "mint",
    "professional":      "ocean",
    "retro":             "sunset",
    "terminal":          "dark",
    "sketch":            "purple",
    "playful-geometric": "xiaohongshu",
}


# ── 主入口 ─────────────────────────────────────────────────────────────────────

def run_generate(
    account_id: int = 1,
    topic_override: str | None = None,
    content_type_override: str | None = None,
    image_mode: str | None = None,   # None = 从图片策略读取; 或手动指定 "cards"|"ai"|"both"
    pillar_override: str | None = None,  # 指定内容方向名称，None = AI 自行覆盖所有方向
    progress_cb=None,  # callable(step: int, data: dict)，每步完成时回调
) -> int:
    """
    为指定账号执行一次内容生成。
    image_mode 为 None 时从 image_strategy 表读取账号配置。
    """
    def _progress(step: int, data: dict | None = None):
        if progress_cb:
            try:
                progress_cb(step, data or {})
            except Exception:
                pass

    _progress(0)  # 准备选题

    # ── 读取账号策略
    c = database.conn()
    strategy_row = c.execute(
        "SELECT data FROM strategy WHERE account_id=? ORDER BY version DESC LIMIT 1",
        (account_id,),
    ).fetchone()
    img_strategy_row = c.execute(
        "SELECT * FROM image_strategy WHERE account_id=?", (account_id,)
    ).fetchone()
    c.close()

    strategy: dict = {}
    if strategy_row:
        try:
            strategy = json.loads(strategy_row["data"])
        except Exception:
            pass

    # 图片策略：优先使用参数，否则读账号配置
    img_cfg: dict = {}
    if img_strategy_row:
        img_cfg = {
            "mode": img_strategy_row["mode"],
            "prompt_template": img_strategy_row["prompt_template"],
            "card_theme": img_strategy_row["card_theme"],
            "reference_images": json.loads(img_strategy_row["reference_images"] or "[]"),
            "ai_model": img_strategy_row["ai_model"],
        }
    else:
        img_cfg = {"mode": "cards", "card_theme": "default",
                   "prompt_template": "", "reference_images": [], "ai_model": None}

    # 读取图片模板：specific=用激活模板，random=从所有模板中随机取一个
    import random as _random_mod
    template_mode = img_cfg.get("template_mode", "specific") if img_cfg else "specific"
    c3 = database.conn()
    active_template_items: list[dict] | None = None
    if template_mode == "random":
        all_tpls = c3.execute(
            "SELECT * FROM image_template WHERE account_id=?", (account_id,)
        ).fetchall()
        if all_tpls:
            chosen = _random_mod.choice(all_tpls)
            active_template_items = json.loads(chosen["items"] or "[]")
            logger.info(f"[generate] 随机模板：{chosen['name']}")
    else:
        active_tpl_row = c3.execute(
            "SELECT * FROM image_template WHERE account_id=? AND is_active=1 LIMIT 1",
            (account_id,),
        ).fetchone()
        if active_tpl_row:
            active_template_items = json.loads(active_tpl_row["items"] or "[]")
    c3.close()

    # 外部 image_mode 参数优先（来自生成面板手动选择）
    resolved_mode = image_mode or img_cfg["mode"]

    # ── 选取内容类型
    if content_type_override:
        # 用户手动指定内容类型
        c2 = database.conn()
        ct_row = c2.execute(
            "SELECT * FROM content_type WHERE account_id=? AND name=? AND is_active=1",
            (account_id, content_type_override),
        ).fetchone()
        c2.close()
        content_type_row = dict(ct_row) if ct_row else None
    else:
        content_type_row = _pick_content_type(account_id)

    if content_type_row is None:
        # 没有配置内容类型时用空模板（仍可生成，提示词用默认）
        from routers.topics import DEFAULT_PROMPT
        content_type_row = {
            "name": content_type_override or "通用",
            "prompt_template": DEFAULT_PROMPT,
        }

    # ── 选题
    if topic_override:
        topic_text = topic_override.strip()
        ct_name = content_type_row["name"]
        logger.info(f"[generate] 手动指定选题：{topic_text}")
    else:
        from routers.topics import pop_next_topic
        topic_row = pop_next_topic(account_id, content_type=content_type_row["name"])
        if topic_row is None:
            topic_row = pop_next_topic(account_id)   # 跨类型兜底
        if topic_row is None:
            logger.warning("[generate] 选题库已耗尽，请在「策略」页面补充选题")
            _notify_topics_low(account_id, remaining=0)
            raise RuntimeError("选题库已耗尽，请在「选题库」页面补充选题后重试")
        topic_text = topic_row["content"]
        ct_name    = topic_row["content_type"]
        logger.info(f"[generate] 从选题库取题：{topic_text}（类型：{ct_name}）")
        # 检查剩余未用选题数，不足 5 条时飞书提醒
        _check_topics_and_notify(account_id)

    # ── 读取该内容类型的提示词模板
    prompt_template = content_type_row["prompt_template"]

    _progress(1)  # AI 生成文案

    # ── AI 生成文案（JSON）
    try:
        result = _ai_generate(
            strategy=strategy,
            topic=topic_text,
            content_type=ct_name,
            prompt_template=prompt_template,
            account_id=account_id,
            pillar_override=pillar_override,
        )
    except Exception as e:
        logger.error(f"[generate] AI 文案生成失败：{e}")
        raise RuntimeError(f"AI 文案生成失败：{e}")

    title       = result.get("title", "").strip()
    content_body = result.get("content", "").strip()
    tags        = result.get("tags", [])

    if not title or not content_body:
        logger.error("[generate] AI 返回的 title/content 为空")
        raise RuntimeError("AI 返回内容为空，请检查 AI 模型配置或提示词模板")

    # ── 确定图片保存目录
    data_dir = os.environ.get("REDBEACON_DATA_DIR") or cfg.get("data_dir", "data")
    img_save_dir = str(Path(data_dir).resolve() / "images")

    _progress(2)  # 生成配图

    # ── 图片生成（根据 image_mode）
    visual_theme = strategy.get("visual_theme", "default")
    ai_images: list[str] = []
    card_paths: list[str] = []

    want_ai    = resolved_mode in ("ai", "both")
    want_cards = resolved_mode in ("cards", "both")

    # 图片提示词：主提示词来自 image_strategy.prompt_template，空时用内置默认
    _DEFAULT_IMG_PROMPT = (
        "小红书封面图，{niche}领域，主题：{title}，"
        "色彩明亮，竖版3:4比例，小红书风格，高质量精美"
    )
    effective_img_prompt = ""
    if want_ai:
        pt = img_cfg.get("prompt_template") or _DEFAULT_IMG_PROMPT
        effective_img_prompt = (
            pt
            .replace("{niche}", strategy.get("niche", ""))
            .replace("{title}", title)
        )

    # 确定图片生成使用的模型（策略 ai_model 优先，否则全局 image_model）
    img_model = img_cfg.get("ai_model") or cfg.get("image_model")

    resolved_items = None
    if want_ai and img_model:
        try:
            from services.image_gen import generate as gen_image
            # 对模板 items 的 prompt 做变量替换（{niche}、{title} 此时已知）
            if active_template_items:
                resolved_items = []
                for item in active_template_items:
                    item_copy = dict(item)
                    if item_copy.get("prompt"):
                        item_copy["prompt"] = (
                            item_copy["prompt"]
                            .replace("{niche}", strategy.get("niche", ""))
                            .replace("{title}", title)
                        )
                    resolved_items.append(item_copy)
            ai_images = gen_image(
                effective_img_prompt,
                img_save_dir,
                model=img_model,
                reference_items=resolved_items if resolved_items is not None else active_template_items,
            )
        except Exception as e:
            logger.warning(f"[generate] AI 图片生成失败（跳过）：{e}")

    # 计算实际写入 DB 的 image_prompt：主提示词 + 模板 item 提示词（与 image_gen._build_messages 一致）
    actual_img_prompt = effective_img_prompt
    if want_ai and resolved_items:
        item_prompts = [it["prompt"] for it in resolved_items if it.get("prompt")]
        if item_prompts:
            parts = ([actual_img_prompt] if actual_img_prompt else []) + item_prompts
            actual_img_prompt = "\n".join(parts)

    card_theme = img_cfg.get("card_theme", "default") if want_cards else "default"
    if want_cards and _RENDERER.exists():
        try:
            card_paths = _render_cards(title, content_body, visual_theme, card_theme,
                                       save_dir=img_save_dir, skip_cover=want_ai and bool(ai_images))
        except Exception as e:
            logger.warning(f"[generate] 卡片渲染失败（跳过）：{e}")

    # AI 封面在前，图文卡片在后
    all_images: list[str] = [*ai_images, *card_paths]

    if not all_images:
        if resolved_mode == "cards":
            # 纯卡片模式渲染失败：渲染器可能未就绪，中止而非产生无图内容
            logger.error(
                "[generate] 卡片渲染失败，已中止入库。请检查渲染器路径是否正确。"
            )
            raise RuntimeError("图文卡片渲染失败，请重试或切换为「AI生图」模式")
        # ai / both 模式：图片失败降级处理，文案仍入库，图片为空，审核时手动补图
        logger.warning(
            f"[generate] 图片生成失败（mode={resolved_mode}），降级入库（图片为空），请在审核时手动补图。"
        )

    _progress(3)  # 加入审核队列

    # ── 写入内容队列
    content_id = _save_to_queue(
        account_id=account_id,
        topic=topic_text,
        content_type=ct_name,
        pillar_name=pillar_override or ct_name,
        title=title,
        body=content_body,
        tags=tags,
        image_prompt=actual_img_prompt,
        image_paths=all_images,
        visual_theme=visual_theme,
    )
    logger.info(f"[generate] 入队成功 id={content_id}  title={title}")
    _progress(4, {"content_id": content_id})  # 完成

    # ── 推送飞书（后台线程，不阻塞主流程）
    import threading
    threading.Thread(target=_push_to_feishu, args=(content_id, account_id), daemon=True).start()

    return 1


# ── AI 文案生成 ────────────────────────────────────────────────────────────────

def _ai_generate(
    strategy: dict,
    topic: str,
    content_type: str,
    prompt_template: str,
    account_id: int = 1,
    pillar_override: str | None = None,
) -> dict:
    """
    调用 AI API，返回解析后的 dict：{title, content, tags}。
    """
    import httpx
    from openai import OpenAI

    api_key  = cfg.get("ai_api_key")
    base_url = cfg.get("ai_base_url", "https://api.openai.com/v1")
    model    = cfg.get("ai_model", "gpt-4o-mini")

    if not api_key:
        raise ValueError("AI API Key 未配置，请在「设置」中填写")

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        http_client=httpx.Client(trust_env=False, timeout=60),
    )

    # 预计算各字段值（供占位符替换和自动追加共用）
    pain_points  = strategy.get("pain_points", [])
    forbidden    = strategy.get("forbidden_words", [])
    pillars      = strategy.get("content_pillars", [])

    if pillar_override:
        matched = next((p for p in pillars if p.get("name") == pillar_override), None)
        pillar_val = (
            f"{pillar_override}（{matched['description']}）"
            if matched and matched.get("description") else pillar_override
        )
    else:
        pillar_val = "、".join(
            p["name"] + (f"（{p['description']}）" if p.get("description") else "")
            for p in pillars if p.get("name")
        )

    # 填充提示词模板占位符（用 replace 而非 .format()，避免模板中的 JSON {} 被误解析）
    filled_prompt = (
        prompt_template
        .replace("{niche}",                strategy.get("niche", "通用"))
        .replace("{target_audience}",      strategy.get("target_audience", "普通用户"))
        .replace("{content_type}",         content_type)
        .replace("{topic}",                topic)
        .replace("{tone}",                 strategy.get("tone", "亲切自然，专业但不刻板，像朋友分享而非说教"))
        .replace("{competitive_advantage}", strategy.get("competitive_advantage", ""))
        .replace("{opening_style}",        strategy.get("opening_style", "提问式或数字列举，前两行必须抓住读者注意力"))
        .replace("{format_style}",         strategy.get("format_style", "分段清晰，多用短句，每段2-3行，重点内容单独成行"))
        .replace("{emoji_usage}",          strategy.get("emoji_usage", "适量，每段1-2个，增加亲切感，不堆砌"))
        .replace("{content_length}",       strategy.get("content_length", "300-500字"))
        .replace("{pain_points}",          " / ".join(pain_points))
        .replace("{forbidden_words}",      " ".join(forbidden))
        .replace("{content_pillars}",      pillar_val)
    )

    # 所有字段均通过占位符控制，不再自动追加——用户拥有完全的提示词控制权

    logger.info(f"[generate] AI model={model}，topic={topic}")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是小红书文案专家。输出格式：严格合法的JSON对象。"
                    "JSON字符串值内部禁止使用英文双引号（\"），"
                    "如需引用，使用「」或""（弯引号）替代。"
                ),
            },
            {"role": "user", "content": filled_prompt},
        ],
        temperature=0.85,
        max_tokens=1500,
    )
    raw = response.choices[0].message.content.strip()
    return _parse_json_output(raw)


def _fix_embedded_quotes(text: str) -> str:
    """Escape unescaped ASCII double quotes inside JSON string values."""
    result = []
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '\\' and in_string:
            result.append(ch)
            i += 1
            if i < len(text):
                result.append(text[i])
            i += 1
            continue
        if ch == '"':
            if not in_string:
                in_string = True
                result.append(ch)
            else:
                # Look ahead to decide: structural closing quote or embedded quote
                rest = text[i + 1:].lstrip(' \t')
                next_ch = rest[0] if rest else ''
                if next_ch in (',', '}', ']', ':'):
                    in_string = False
                    result.append(ch)
                else:
                    result.append('\\"')
        else:
            result.append(ch)
        i += 1
    return ''.join(result)


def _parse_json_output(raw: str) -> dict:
    """
    从 AI 输出中提取 JSON。
    支持：纯 JSON、```json ... ``` 代码块、或文字包裹中的 JSON。
    """
    def _try(text: str) -> dict | None:
        try:
            return json.loads(text)
        except Exception:
            pass
        try:
            return json.loads(_fix_embedded_quotes(text))
        except Exception:
            pass
        return None

    # 尝试直接解析
    r = _try(raw)
    if r is not None:
        return r

    # 提取 ```json ... ``` 代码块（贪婪匹配确保捕获完整 JSON）
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", raw)
    if m:
        r = _try(m.group(1))
        if r is not None:
            return r

    # 最宽松：找第一个 { 到最后一个 }
    start = raw.find("{")
    end   = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        r = _try(raw[start:end + 1])
        if r is not None:
            return r

    logger.warning(f"[generate] 无法解析 AI JSON 输出，原文前200字：{raw[:200]}")
    lines = raw.splitlines()
    title = next((l.replace("标题：", "").replace("标题:", "").strip() for l in lines if "标题" in l), "")
    content_lines = [l for l in lines if l and "标题" not in l and "选题" not in l]
    return {
        "title": title or "无标题",
        "content": "\n".join(content_lines[:20]),
        "tags": [],
    }


# ── 图文卡片渲染 ───────────────────────────────────────────────────────────────

def _render_cards(title: str, body: str, visual_theme: str, card_theme: str = "default", save_dir: str | None = None, skip_cover: bool = False) -> list[str]:
    import random as _random
    import shutil
    if card_theme == "random":
        style = _random.choice(list(_THEME_MAP.values()))
    else:
        # card_theme from image_strategy overrides visual_theme from account strategy
        style = _THEME_MAP.get(card_theme, _THEME_MAP.get(visual_theme, "elegant"))

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        md_path = f.name
        f.write(f"---\ntitle: {title}\n---\n\n{body}")

    tmp_dir = Path(tempfile.mkdtemp(prefix="redbeacon_render_"))
    try:
        # frozen: _RENDERER 是独立二进制，直接执行；开发: 用 sys.executable 运行 .py
        if getattr(sys, "frozen", False) or not str(_RENDERER).endswith(".py"):
            cmd = [str(_RENDERER), md_path, "--output-dir", str(tmp_dir), "--style", style]
        else:
            cmd = [sys.executable, str(_RENDERER), md_path, "--output-dir", str(tmp_dir), "--style", style]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"渲染器退出码 {result.returncode}: {result.stderr[-300:]}")

        all_pngs = sorted(tmp_dir.glob("*.png"), key=lambda p: (p.name != "cover.png", p.name))
        tmp_images = [p for p in all_pngs if not (skip_cover and p.name == "cover.png")]

        # 移动到持久化目录，避免重启后 /tmp 被清空
        if save_dir:
            out_dir = Path(save_dir) / f"cards_{int(time.time())}"
            out_dir.mkdir(parents=True, exist_ok=True)
            final = []
            for p in tmp_images:
                dest = out_dir / p.name
                shutil.move(str(p), str(dest))
                final.append(str(dest))
            return final

        return [str(p) for p in tmp_images]
    finally:
        # 清理临时文件和目录，防止磁盘泄漏
        try:
            Path(md_path).unlink(missing_ok=True)
        except Exception:
            pass
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


# ── 数据库写入 ─────────────────────────────────────────────────────────────────

def _save_to_queue(
    account_id: int,
    topic: str,
    content_type: str,
    title: str,
    body: str,
    tags: list,
    image_prompt: str,
    image_paths: list[str],
    visual_theme: str,
    pillar_name: str | None = None,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    c = database.conn()
    c.execute(
        """INSERT INTO content_queue
           (account_id, topic, content_type, pillar_name, title, body,
            tags, image_prompt, images, visual_theme, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_review', ?, ?)""",
        (
            account_id, topic, content_type, pillar_name or content_type,
            title, body,
            json.dumps(tags, ensure_ascii=False),
            image_prompt,
            json.dumps(image_paths, ensure_ascii=False),
            visual_theme, now, now,
        ),
    )
    c.commit()
    content_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    c.close()
    return content_id


# ── 选题库低余量飞书提醒 ────────────────────────────────────────────────────────

def _notify_topics_low(account_id: int, remaining: int) -> None:
    app_id     = cfg.get("feishu_app_id")
    app_secret = cfg.get("feishu_app_secret")
    if not all([app_id, app_secret]):
        return
    c0 = database.conn()
    acc = c0.execute(
        "SELECT feishu_user_id, display_name, nickname FROM account WHERE id=?",
        (account_id,),
    ).fetchone()
    c0.close()
    if not acc:
        return
    user_id = acc["feishu_user_id"] or cfg.get("feishu_user_id", "")
    if not user_id:
        return
    acc_name = acc["display_name"] or acc["nickname"] or f"账号 {account_id}"
    if remaining == 0:
        msg = f"[{acc_name}] 选题库已耗尽，无法继续生成内容，请尽快补充选题。"
    else:
        msg = f"[{acc_name}] 选题库仅剩 {remaining} 条，建议尽快补充，避免内容断更。"
    from services.feishu_api import FeishuAPI
    app_token = cfg.get("feishu_app_token", "")
    table_id  = cfg.get("feishu_table_id", "")
    feishu = FeishuAPI(app_id, app_secret, app_token, table_id)
    try:
        feishu.send_text_message(user_id, msg)
        logger.info(f"[generate] 飞书选题低余量提醒已发送（账号 {account_id}，剩余 {remaining}）")
    except Exception as e:
        logger.warning(f"[generate] 飞书选题提醒发送失败：{e}")


def _check_topics_and_notify(account_id: int) -> None:
    c = database.conn()
    row = c.execute(
        "SELECT COUNT(*) AS cnt FROM topic WHERE account_id=? AND is_used=0",
        (account_id,),
    ).fetchone()
    c.close()
    remaining = row["cnt"] if row else 0
    if remaining < 5:
        import threading
        threading.Thread(
            target=_notify_topics_low,
            args=(account_id, remaining),
            daemon=True,
        ).start()


# ── 飞书推送 ───────────────────────────────────────────────────────────────────

# 飞书多维表格模板（固定，所有用户共用同一张表结构）
_FEISHU_APP_TOKEN = "Wf0WbW4R0a9pcJs4bm6cGEuKn7e"
_FEISHU_TABLE_ID  = "tblGEBTJoqK6snYP"


def _push_to_feishu(content_id: int, account_id: int = 1) -> None:
    app_id     = cfg.get("feishu_app_id")
    app_secret = cfg.get("feishu_app_secret")

    if not all([app_id, app_secret]):
        logger.warning("[generate] 飞书推送跳过：app_id 或 app_secret 未配置")
        return

    # 从 account 表读取该账号的飞书表格配置（已从 settings 迁移到 account）
    c0 = database.conn()
    acc = c0.execute(
        "SELECT feishu_app_token, feishu_table_id, feishu_user_id FROM account WHERE id=?",
        (account_id,),
    ).fetchone()
    c0.close()
    app_token = (acc["feishu_app_token"] if acc else None) or _FEISHU_APP_TOKEN
    table_id  = (acc["feishu_table_id"]  if acc else None) or _FEISHU_TABLE_ID
    user_id   = (acc["feishu_user_id"]   if acc else None) or cfg.get("feishu_user_id", "")

    from services.feishu_api import (
        FeishuAPI, FIELD_TITLE, FIELD_BODY, FIELD_TAGS,
        FIELD_IMAGES, FIELD_STATUS, STATUS_PENDING,
    )

    c = database.conn()
    row = c.execute(
        "SELECT title, body, tags, images FROM content_queue WHERE id=?",
        (content_id,),
    ).fetchone()
    c.close()
    if row is None:
        return

    feishu = FeishuAPI(app_id, app_secret, app_token, table_id)
    try:
        images = json.loads(row["images"] or "[]")
        image_tokens = []
        for img_path in images:
            try:
                token = feishu.upload_image(img_path)
                image_tokens.append({"file_token": token})
            except Exception as e:
                logger.warning(f"[generate] 飞书图片上传失败 {img_path}：{e}")

        # 标签列表 → "、"分隔的字符串
        try:
            tags_list = json.loads(row["tags"] or "[]")
        except Exception:
            tags_list = []
        tags_str = "、".join(t.lstrip("#") for t in tags_list if t)

        fields = {
            FIELD_TITLE:  row["title"] or "",
            FIELD_BODY:   row["body"] or "",
        }
        if tags_str:
            fields[FIELD_TAGS] = tags_str
        if image_tokens:
            fields[FIELD_IMAGES] = image_tokens

        record_id = feishu.add_record(fields)
        c2 = database.conn()
        c2.execute("UPDATE content_queue SET feishu_record_id=? WHERE id=?", (record_id, content_id))
        c2.commit()
        c2.close()
        logger.info(f"[generate] 飞书推送成功：content_id={content_id} record_id={record_id}")

        if user_id:
            try:
                table_url = f"https://feishu.cn/base/{app_token}"
                feishu.send_text_message(
                    user_id,
                    f"📝 新文案已生成，等待审核\n《{row['title']}》\n\n点击审核：{table_url}"
                )
            except Exception as e:
                logger.warning(f"[generate] 飞书消息通知失败：{e}")
    except Exception as e:
        logger.error(f"[generate] 飞书推送失败：{e}")


# ── 工具函数 ───────────────────────────────────────────────────────────────────

def _pick_content_type(account_id: int) -> dict | None:
    """
    轮询选取激活的内容类型：选最近生成次数最少的那个。
    """
    c = database.conn()
    types = c.execute(
        "SELECT * FROM content_type WHERE account_id=? AND is_active=1 ORDER BY sort_order, id",
        (account_id,),
    ).fetchall()
    if not types:
        c.close()
        return None

    # 统计每个类型最近的生成次数
    counts = {}
    for t in types:
        row = c.execute(
            "SELECT COUNT(*) as n FROM content_queue WHERE account_id=? AND content_type=?",
            (account_id, t["name"]),
        ).fetchone()
        counts[t["name"]] = row["n"] if row else 0
    c.close()

    best = min(types, key=lambda t: counts.get(t["name"], 0))
    return dict(best)
