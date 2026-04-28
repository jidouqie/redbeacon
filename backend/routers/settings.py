"""全局设置：AI Key、飞书 App 凭证等。"""
import os
import sys
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

import config
from utils.logger import get_logger

router = APIRouter()
logger = get_logger("router.settings")


# ── Schema ─────────────────────────────────────────────────────────────────────

class SettingItem(BaseModel):
    key: str
    value: str


class SettingsBatch(BaseModel):
    items: list[SettingItem]


# ── 路由 ───────────────────────────────────────────────────────────────────────

@router.get("")
def get_public_settings():
    """返回所有配置（加密字段返回哨兵值 '__SET__'）。"""
    return config.get_all_public()


@router.put("/{key}")
def set_setting(key: str, body: SettingItem):
    config.set(key, body.value)
    logger.info(f"配置已更新：{key}")
    return {"ok": True}


@router.post("/batch")
def set_settings_batch(body: SettingsBatch):
    for item in body.items:
        # 跳过前端回传的哨兵值（用户没有修改该字段）
        if item.value == config._SENTINEL:
            continue
        config.set(item.key, item.value)
    logger.info(f"批量配置更新：{[i.key for i in body.items]}")
    return {"ok": True, "updated": len(body.items)}


@router.get("/pick-file")
def pick_file():
    """调用 macOS 原生文件选择框，返回所选文件的绝对路径。"""
    import subprocess, sys
    if sys.platform != "darwin":
        raise HTTPException(400, "文件选择仅支持 macOS")
    result = subprocess.run(
        ["osascript", "-e", "POSIX path of (choose file)"],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        return {"path": None}
    return {"path": result.stdout.strip()}


@router.get("/pick-folder")
def pick_folder():
    """调用 macOS 原生目录选择框，返回所选目录的绝对路径。"""
    import subprocess, sys
    if sys.platform != "darwin":
        raise HTTPException(400, "目录选择仅支持 macOS")
    result = subprocess.run(
        ["osascript", "-e", "POSIX path of (choose folder)"],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        return {"path": None}
    return {"path": result.stdout.strip().rstrip("/")}


@router.get("/models")
def list_models():
    """从配置的 AI API 直接请求 /v1/models，返回完整模型列表。"""
    import httpx

    api_key  = config.get("ai_api_key")
    base_url = config.get("ai_base_url", "https://api.openai.com/v1").rstrip("/")
    if not api_key:
        raise HTTPException(400, "AI API Key 未配置")
    try:
        with httpx.Client(trust_env=False, timeout=15) as client:
            resp = client.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"[models] 原始响应 keys={list(data.keys()) if isinstance(data, dict) else type(data).__name__}, 完整内容={str(data)[:500]}")

        ids: list[str] = []

        # 标准 OpenAI 格式: {"object":"list","data":[{"id":"..."},...]}
        if isinstance(data, dict) and "data" in data:
            for m in data["data"]:
                mid = m.get("id") if isinstance(m, dict) else str(m)
                if mid:
                    ids.append(mid)
        # 部分代理直接返回列表
        elif isinstance(data, list):
            for m in data:
                mid = m.get("id") if isinstance(m, dict) else str(m)
                if mid:
                    ids.append(mid)
        # 部分代理把模型放在其他字段
        elif isinstance(data, dict):
            for key in ("models", "result", "items"):
                if key in data and isinstance(data[key], list):
                    for m in data[key]:
                        mid = m.get("id") if isinstance(m, dict) else str(m)
                        if mid:
                            ids.append(mid)
                    break

        ids = sorted(set(ids))
        logger.info(f"[models] 解析到 {len(ids)} 个模型")
        # 即使 0 个也返回，前端会提示；raw 字段用于调试
        raw_preview = str(data)[:300] if not isinstance(data, dict) else {k: str(v)[:100] for k, v in list(data.items())[:5]}
        return {"models": ids, "raw_keys": list(data.keys()) if isinstance(data, dict) else str(type(data)), "raw": raw_preview}
    except Exception as e:
        raise HTTPException(502, f"获取模型列表失败：{e}")


@router.post("/test-ai")
def test_ai_connection():
    import httpx
    from openai import OpenAI

    api_key  = config.get("ai_api_key")
    base_url = config.get("ai_base_url", "https://api.openai.com/v1")
    model    = config.get("ai_model", "gpt-4o-mini")
    if not api_key:
        raise HTTPException(400, "AI API Key 未配置")
    try:
        client = OpenAI(
            api_key=api_key, base_url=base_url,
            http_client=httpx.Client(trust_env=False, timeout=20),
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": '回复"ok"两个字'}],
            max_tokens=10,
        )
        return {"ok": True, "reply": resp.choices[0].message.content.strip(), "model": model}
    except Exception as e:
        raise HTTPException(502, f"连接失败：{e}")


@router.post("/test-image")
def test_image_connection():
    import httpx

    api_key   = config.get("ai_api_key")
    base_url  = config.get("ai_base_url", "https://api.openai.com/v1").rstrip("/")
    img_model = config.get("image_model", "")
    if not api_key:
        raise HTTPException(400, "AI API Key 未配置")
    if not img_model:
        raise HTTPException(400, "图片模型未配置")
    try:
        with httpx.Client(trust_env=False, timeout=15) as client:
            resp = client.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data") or (data if isinstance(data, list) else [])
        ids = [m.get("id") if isinstance(m, dict) else m for m in items]
        found = img_model in ids
        return {"ok": True, "model": img_model, "found_in_list": found, "available": ids[:30]}
    except Exception as e:
        raise HTTPException(502, f"连接失败：{e}")


# ── 飞书认证测试 ────────────────────────────────────────────────────────────────

@router.post("/test-feishu-auth")
def test_feishu_auth():
    """只验证飞书 App ID + App Secret 是否有效（获取 tenant_access_token）。"""
    import requests as req

    app_id     = config.get("feishu_app_id")
    app_secret = config.get("feishu_app_secret")
    if not app_id or not app_secret:
        raise HTTPException(400, "请先填写 App ID 和 App Secret")

    FEISHU = "https://open.feishu.cn/open-apis"
    r = req.post(
        f"{FEISHU}/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret}, timeout=15,
    )
    r.raise_for_status()
    rb = r.json()
    if rb.get("code") != 0:
        raise HTTPException(400, f"飞书认证失败：{rb.get('msg')}")
    return {"ok": True, "msg": "✓ App ID / Secret 验证通过"}


@router.get("/feishu-users")
def get_feishu_users():
    """用当前 App ID/Secret 拉取企业成员列表，返回 user_id + name，用于选择通知接收人。"""
    import requests as req

    app_id     = config.get("feishu_app_id")
    app_secret = config.get("feishu_app_secret")
    if not app_id or not app_secret:
        raise HTTPException(400, "请先填写 App ID 和 App Secret")

    FEISHU = "https://open.feishu.cn/open-apis"
    r = req.post(
        f"{FEISHU}/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret}, timeout=15,
    )
    r.raise_for_status()
    rb = r.json()
    if rb.get("code") != 0:
        raise HTTPException(400, f"飞书认证失败：{rb.get('msg')}")
    token = rb["tenant_access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    u_r = req.get(
        f"{FEISHU}/contact/v3/users",
        headers=headers,
        params={"page_size": 50, "user_id_type": "user_id"},
        timeout=15,
    )
    if u_r.status_code != 200:
        raise HTTPException(502, f"获取成员列表失败：HTTP {u_r.status_code}")
    ud = u_r.json()
    if ud.get("code") != 0:
        raise HTTPException(400, f"飞书错误：{ud.get('msg')}（需要 contact:user:readonly 权限）")

    users = [
        {"user_id": u.get("user_id", ""), "name": u.get("name", "")}
        for u in (ud.get("data", {}).get("items") or [])
        if u.get("user_id")
    ]
    return {"users": users}


# ── 代理管理 ────────────────────────────────────────────────────────────────────

@router.post("/proxy/test")
async def test_proxy():
    """调用一次代理 API，验证能否取到 IP，不写入数据库。"""
    from services.proxy_service import fetch_fresh_proxy
    if not config.get("proxy_api_url", "").strip():
        raise HTTPException(400, "未配置代理 API 地址")
    proxy = fetch_fresh_proxy()
    if not proxy:
        raise HTTPException(502, "调用代理 API 失败或无法解析响应，请检查 URL 和余额")
    return {"ok": True, "proxy": proxy}


# ── 运行日志 ────────────────────────────────────────────────────────────────────

@router.get("/logs")
def get_app_logs(tail: int = 150):
    """读取 redbeacon.log 最后 N 行，供前端日志面板展示。"""
    _BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent.parent))
    log_dir  = os.environ.get("REDBEACON_LOG_DIR", str(_BASE / "logs"))
    log_file = Path(log_dir) / "redbeacon.log"
    if not log_file.exists():
        return {"lines": []}
    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return {"lines": [l.rstrip("\n") for l in lines[-tail:]]}
    except Exception as e:
        raise HTTPException(500, f"读取日志失败：{e}")
