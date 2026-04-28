"""
AI 图片生成服务。
支持两种模式：
  1. 纯文生图：只传 prompt
  2. 图生图（多模态）：传 items 列表，每项含 image_path（本地路径或 base64 data URL）+ prompt
"""
import base64
import re
import time
from pathlib import Path

import config as cfg
from utils.logger import get_logger

logger = get_logger("image_gen")


def generate(
    prompt: str,
    save_dir: str,
    model: str | None = None,
    count: int = 1,
    reference_items: list[dict] | None = None,
) -> list[str]:
    """
    生成图片，保存为 JPG，返回已保存文件的绝对路径列表。

    reference_items: list of {"image_path": str, "prompt": str}
      - image_path 为空 → 纯文生图
      - image_path 非空 → 图生图，把图片 base64 编码后随 prompt 一起发送
      - 多个 item → 所有图片拼入同一条消息，各项 prompt 按顺序拼接
    """
    import httpx
    from openai import OpenAI

    api_key  = cfg.get("ai_api_key")
    base_url = cfg.get("ai_base_url", "https://api.openai.com/v1")
    model    = model or cfg.get("image_model", "")

    if not api_key:
        logger.warning("[image_gen] AI API Key 未配置，跳过图片生成")
        return []
    if not model:
        logger.warning("[image_gen] 图片模型未配置，跳过图片生成")
        return []

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        max_retries=0,
        http_client=httpx.Client(trust_env=False, timeout=180),
    )

    messages = _build_messages(prompt, reference_items)

    has_ref = bool(reference_items and any(i.get("image_path") for i in reference_items))
    logger.info(f"[image_gen] 生成图片 x{count}，model={model}，有参考图={has_ref}")

    results: list[str] = []
    for i in range(count):
        last_err = None
        for attempt in range(3):  # 最多重试 2 次（共 3 次）
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    modalities=["image", "text"],
                )
                raw_content = resp.choices[0].message.content
                b64_list = _extract_b64(raw_content)
                if b64_list:
                    for b64 in b64_list:
                        path = _save_bytes(base64.b64decode(b64), save_dir)
                        results.append(path)
                else:
                    logger.warning(f"[image_gen] 第{i+1}张响应中未找到图片数据，content类型={type(raw_content).__name__}")
                last_err = None
                break
            except Exception as e:
                last_err = e
                if attempt < 2:
                    logger.warning(f"[image_gen] 第{i+1}张第{attempt+1}次失败，5s 后重试：{e}")
                    time.sleep(5)
        if last_err is not None:
            logger.warning(f"[image_gen] 第{i+1}张生成失败，跳过：{last_err}")

    return results


def _extract_b64(content) -> list[str]:
    """从 content 中提取所有 base64 图片数据，兼容字符串和 parts 列表两种格式。"""
    if not content:
        return []

    # 格式一：content 是字符串（内嵌 data URL）
    if isinstance(content, str):
        return re.findall(r"data:image/\w+;base64,([A-Za-z0-9+/=]+)", content)

    # 格式二：content 是 parts 列表（Gemini / 多模态接口常见格式）
    results: list[str] = []
    parts = content if isinstance(content, list) else []
    for part in parts:
        if not isinstance(part, dict):
            # pydantic 对象（openai SDK 返回）
            part_type = getattr(part, "type", None)
            if part_type == "image_url":
                url = getattr(getattr(part, "image_url", None), "url", "") or ""
                m = re.search(r"data:image/\w+;base64,([A-Za-z0-9+/=]+)", url)
                if m:
                    results.append(m.group(1))
            elif part_type == "text":
                text = getattr(part, "text", "") or ""
                results.extend(re.findall(r"data:image/\w+;base64,([A-Za-z0-9+/=]+)", text))
        else:
            if part.get("type") == "image_url":
                url = (part.get("image_url") or {}).get("url", "") or ""
                m = re.search(r"data:image/\w+;base64,([A-Za-z0-9+/=]+)", url)
                if m:
                    results.append(m.group(1))
            elif part.get("type") == "text":
                results.extend(re.findall(r"data:image/\w+;base64,([A-Za-z0-9+/=]+)",
                                          part.get("text", "") or ""))
    return results


def _build_messages(prompt: str, reference_items: list[dict] | None) -> list[dict]:
    """把 reference_items + prompt 组装成 OpenAI 多模态 messages。"""
    has_images = reference_items and any(i.get("image_path") for i in reference_items)

    # 无论是否有参考图，都先收集模板 item 的 prompt（避免纯文生图时漏掉 item 提示词）
    item_prompts: list[str] = []
    for item in (reference_items or []):
        ip = item.get("prompt", "")
        if ip:
            item_prompts.append(ip)

    if not has_images:
        # 纯文生图：主提示词 + item prompts 合并
        all_parts = ([prompt] if prompt else []) + item_prompts
        combined = "\n".join(all_parts) if all_parts else ""
        full_prompt = (
            combined + "\n\n竖版构图，3:4比例，小红书封面风格，高质量，精美细腻。"
            if len(combined) < 200 else combined
        )
        return [{"role": "user", "content": full_prompt}]

    # 图生图：先放图片 parts，再放合并后的文本 prompt
    content_parts: list[dict] = []
    for item in (reference_items or []):
        img_path = item.get("image_path", "")
        if not img_path:
            continue
        data_url = _to_data_url(img_path)
        if data_url:
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": data_url},
            })

    all_prompts = ([prompt] if prompt else []) + item_prompts
    final_text = "\n".join(all_prompts) if all_prompts else "按参考图风格生成"
    final_text += "\n\n竖版构图，3:4比例，小红书封面风格，高质量，精美细腻。"

    content_parts.append({"type": "text", "text": final_text})
    return [{"role": "user", "content": content_parts}]


def _resolve_image_path(image_path: str) -> Path:
    """相对路径拼接 data_dir，绝对路径直接用（兼容旧记录）。"""
    import os as _os
    p = Path(image_path)
    if p.is_absolute():
        return p
    data_dir = Path(_os.environ.get("REDBEACON_DATA_DIR", "data")).resolve()
    return (data_dir / p).resolve()


def _to_data_url(image_path: str) -> str | None:
    if not image_path:
        return None
    if image_path.startswith("data:"):
        return image_path
    try:
        p = _resolve_image_path(image_path)
        if not p.exists():
            logger.warning(f"[image_gen] 参考图片不存在：{image_path}")
            return None
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}
        mime = mime_map.get(p.suffix.lower(), "image/jpeg")
        b64 = base64.b64encode(p.read_bytes()).decode()
        return f"data:{mime};base64,{b64}"
    except Exception as e:
        logger.warning(f"[image_gen] 参考图片读取失败 {image_path}：{e}")
        return None


def _save_bytes(data: bytes, save_dir: str) -> str:
    Path(save_dir).mkdir(parents=True, exist_ok=True)
    filename = f"ai_image_{int(time.time() * 1000)}.jpg"
    file_path = Path(save_dir) / filename
    file_path.write_bytes(data)
    logger.info(f"[image_gen] 图片已保存：{file_path}")
    return str(file_path)
