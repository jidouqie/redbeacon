"""
账号管理：创建、登录（扫码）、状态查询、mcp 进程控制、飞书表格配置。

路由结构：
  GET    /api/accounts              ← 列出所有账号
  POST   /api/accounts              ← 新建账号（受 max_accounts 限制）
  GET    /api/accounts/{id}         ← 获取单个账号
  PATCH  /api/accounts/{id}         ← 更新备注名 / 飞书表格配置
  DELETE /api/accounts/{id}         ← 删除账号

  POST   /api/accounts/{id}/login/start   ← 启动 mcp，准备扫码
  GET    /api/accounts/{id}/login/qr      ← 获取二维码（base64）
  GET    /api/accounts/{id}/login/status  ← 轮询登录状态，成功后写 DB
  GET    /api/accounts/{id}/login/verify  ← 手动验证登录（直接调 MCP）
  DELETE /api/accounts/{id}/login         ← 退出登录，清除 cookie

  POST   /api/accounts/{id}/mcp/start
  POST   /api/accounts/{id}/mcp/stop
  GET    /api/accounts/{id}/mcp/status
  GET    /api/accounts/{id}/mcp/logs

  POST   /api/accounts/{id}/feishu/setup  ← 自动复制模板表格
  POST   /api/accounts/{id}/feishu/test   ← 测试表格读写 + 消息发送

免费版 MAX_ACCOUNTS=1，打包进二进制，不从数据库读，用户无法篡改。
专业版改 MAX_ACCOUNTS 常量后重新打包。
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests as http
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# 账号数量上限：编译进二进制，用户无法通过修改数据库绕过。
# 专业版发布时改此常量后重新打包即可。
MAX_ACCOUNTS = 1

import config as cfg
import database
import services.mcp_manager as mcp_manager
from utils.logger import get_logger

router = APIRouter()
logger = get_logger("router.account")

_MCP_TIMEOUT = 60    # mcp 接口超时秒数（首次请求需启动浏览器，最多 60s）
_NO_PROXY = {"http": "", "https": ""}   # 不通过系统代理，直连本地 mcp


# ── Schema ─────────────────────────────────────────────────────────────────────

class AccountOut(BaseModel):
    id: int
    display_name: str | None
    nickname: str | None
    xhs_user_id: str | None
    login_status: str
    mcp_port: int
    mcp_running: bool
    mcp_headless: bool
    proxy: str | None
    last_login_check: str | None
    feishu_app_token: str | None
    feishu_table_id: str | None
    feishu_user_id: str | None
    auto_generate_enabled: bool
    generate_schedule_json: str | None


class AccountCreate(BaseModel):
    mcp_port: int = 18060
    proxy: str | None = None


class AccountUpdate(BaseModel):
    display_name: str | None = None
    proxy: str | None = None
    feishu_app_token: str | None = None
    feishu_table_id: str | None = None
    feishu_user_id: str | None = None
    mcp_headless: bool | None = None
    auto_generate_enabled: bool | None = None
    generate_schedule_json: str | None = None


class FeishuSetupIn(BaseModel):
    app_token: str | None = None
    table_id:  str | None = None


# ── 账号 CRUD ──────────────────────────────────────────────────────────────────

@router.get("", response_model=list[AccountOut])
def list_accounts():
    c = database.conn()
    rows = c.execute("SELECT * FROM account ORDER BY id").fetchall()
    c.close()
    return [_row_to_out(r) for r in rows]


@router.get("/{account_id}", response_model=AccountOut)
def get_account(account_id: int):
    return _get_or_404(account_id)


_DEFAULT_IMG_PROMPT = (
    "小红书封面图，{niche}领域，主题：{title}，"
    "色彩明亮，竖版3:4比例，小红书风格，高质量精美"
)

_DEFAULT_IMG_TEMPLATE_ITEMS = json.dumps([
    {
        "image_path": "",
        "prompt": (
            "小红书封面，主题关键词突出，色彩明亮饱和，构图精美，"
            "竖版3:4比例，高质量细腻，无文字叠加，背景简洁，主体清晰"
        ),
    }
], ensure_ascii=False)


@router.post("", response_model=AccountOut, status_code=201)
def create_account(body: AccountCreate):
    """新建账号，受 MAX_ACCOUNTS 常量限制。"""
    max_accounts = MAX_ACCOUNTS
    c = database.conn()
    count = c.execute("SELECT COUNT(*) FROM account").fetchone()[0]
    if count >= max_accounts:
        c.close()
        raise HTTPException(
            403,
            {"code": "ACCOUNT_LIMIT", "max": max_accounts}
        )
    # 取已有最大端口+1，删账号不会影响其他账号的端口，也不会出现重复
    if body.mcp_port:
        port = body.mcp_port
    else:
        max_port = c.execute("SELECT MAX(mcp_port) FROM account").fetchone()[0]
        port = (max_port + 1) if max_port is not None else 18060
    now = datetime.now(timezone.utc).isoformat()
    c.execute(
        "INSERT INTO account (mcp_port, proxy, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (port, body.proxy, now, now),
    )
    c.commit()
    account_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]

    # 设置默认显示名
    c.execute("UPDATE account SET display_name=? WHERE id=?", (f"redbeacon-{account_id}", account_id))

    # 初始化图片策略（含默认提示词）
    c.execute(
        """INSERT OR IGNORE INTO image_strategy
               (account_id, mode, prompt_template, card_theme, reference_images, ai_model, updated_at)
           VALUES (?, 'cards', ?, 'default', '[]', NULL, ?)""",
        (account_id, _DEFAULT_IMG_PROMPT, now),
    )
    # 创建默认图片模板（未激活，用户可按需激活）
    c.execute(
        """INSERT INTO image_template (account_id, name, is_active, items, created_at, updated_at)
           VALUES (?, '默认文生图', 0, ?, ?, ?)""",
        (account_id, _DEFAULT_IMG_TEMPLATE_ITEMS, now, now),
    )
    c.commit()
    row = c.execute("SELECT * FROM account WHERE id=?", (account_id,)).fetchone()
    c.close()
    return _row_to_out(row)


@router.patch("/{account_id}", response_model=AccountOut)
def update_account_meta(account_id: int, body: AccountUpdate):
    """更新账号备注名、飞书表格配置或 MCP 启动模式。"""
    updates: dict = {}
    if body.display_name is not None:
        updates["display_name"] = body.display_name or None
    if body.proxy is not None:
        updates["proxy"] = body.proxy or None
    if body.feishu_app_token is not None:
        updates["feishu_app_token"] = body.feishu_app_token or None
    if body.feishu_table_id is not None:
        updates["feishu_table_id"] = body.feishu_table_id or None
    if body.feishu_user_id is not None:
        updates["feishu_user_id"] = body.feishu_user_id or None
    if body.mcp_headless is not None:
        updates["mcp_headless"] = 1 if body.mcp_headless else 0
    schedule_changed = False
    if body.auto_generate_enabled is not None:
        updates["auto_generate_enabled"] = 1 if body.auto_generate_enabled else 0
        schedule_changed = True
    if body.generate_schedule_json is not None:
        updates["generate_schedule_json"] = body.generate_schedule_json or None
        schedule_changed = True
    if updates:
        _update_account(account_id, **updates)

    # 排期变更时重建调度器任务
    if schedule_changed:
        import scheduler as sched
        sched.restart()
        logger.info(f"[account] 账号 {account_id} 排期已更新，调度器已重建")

    # 若 headless 设置变更且 MCP 正在运行，自动重启使其生效
    if body.mcp_headless is not None and mcp_manager.is_running(account_id):
        c = database.conn()
        acc = c.execute("SELECT cookie_file, mcp_port FROM account WHERE id=?", (account_id,)).fetchone()
        c.close()
        if acc and acc["cookie_file"]:
            mcp_manager.stop(account_id)
            pid = mcp_manager.start(account_id, acc["mcp_port"], acc["cookie_file"],
                                    None, headless=body.mcp_headless)
            _update_account(account_id, mcp_pid=pid)
            logger.info(f"[mcp] 账号 {account_id} headless={body.mcp_headless}，MCP 已重启 PID={pid}")

    return _get_or_404(account_id)


@router.delete("/{account_id}", status_code=204)
def delete_account(account_id: int):
    """删除账号及所有关联数据，同时停止其 mcp 进程。"""
    mcp_manager.stop(account_id)
    c = database.conn()
    # 按外键依赖顺序删除：子表先删，主表最后
    c.execute("DELETE FROM publish_log WHERE account_id=?", (account_id,))
    c.execute("DELETE FROM content_queue WHERE account_id=?", (account_id,))
    c.execute("DELETE FROM prompt WHERE account_id=?", (account_id,))
    c.execute("DELETE FROM strategy WHERE account_id=?", (account_id,))
    c.execute("DELETE FROM topic WHERE account_id=?", (account_id,))
    c.execute("DELETE FROM content_type WHERE account_id=?", (account_id,))
    c.execute("DELETE FROM image_template WHERE account_id=?", (account_id,))
    c.execute("DELETE FROM image_strategy WHERE account_id=?", (account_id,))
    c.execute("DELETE FROM account WHERE id=?", (account_id,))
    c.commit()
    c.close()


# ── 扫码登录 ───────────────────────────────────────────────────────────────────

@router.post("/{account_id}/login/start")
def login_start(account_id: int):
    """
    启动 xiaohongshu-login 独立登录工具。
    该工具自带 GUI 窗口，用户扫码后自动将 cookie 写入 COOKIES_PATH。
    前端轮询 /login/status（检测 cookie 文件是否出现）等待登录成功。
    """
    row = _get_or_404(account_id)

    data_dir = os.environ.get("REDBEACON_DATA_DIR") or cfg.get("data_dir", "data")
    cookie_path = str(Path(data_dir).resolve() / f"cookies_{account_id}.json")

    # 保存 cookie 路径供后续 mcp/start 使用
    _update_account(account_id, cookie_file=cookie_path)

    try:
        login_bin = mcp_manager._login_binary()
    except FileNotFoundError as e:
        raise HTTPException(400, str(e))

    # 确保 cookie 目录存在
    Path(cookie_path).parent.mkdir(parents=True, exist_ok=True)

    # 停止正在运行的 MCP 进程：避免 MCP 持有 cookie 文件句柄或端口，干扰登录
    if mcp_manager.is_running(account_id):
        logger.info(f"[login] account {account_id} 停止现有 MCP 进程，准备登录")
        mcp_manager.stop(account_id)
        _update_account(account_id, mcp_pid=None)
        time.sleep(1)

    # 删除旧 cookie 文件：login 工具启动时若发现 cookie 有效会立即退出（闪退）
    # 用户点击"扫码登录"时始终期望重新扫码，必须先清空旧 session
    if Path(cookie_path).exists():
        try:
            Path(cookie_path).unlink()
            logger.info(f"[login] account {account_id} 已清除旧 cookie，准备重新扫码")
        except Exception as e:
            logger.warning(f"[login] 清除旧 cookie 失败：{e}")

    import subprocess as _sp, sys as _sys, shlex as _shlex

    if _sys.platform == "darwin":
        # macOS：通过 osascript 在 Terminal 中启动，并 activate 保证窗口弹到前台。
        # 登录是本地用户操作，不传代理。
        env_prefix = f"COOKIES_PATH={_shlex.quote(cookie_path)}"
        cmd = f"{env_prefix} {_shlex.quote(str(login_bin))}"
        # 用 AppleScript 多行语句：do script 后立即 activate，确保 Terminal 弹到前台
        apple_script = (
            f'tell application "Terminal"\n'
            f'    do script "{cmd}"\n'
            f'    activate\n'
            f'end tell'
        )
        result = _sp.run(
            ["osascript", "-e", apple_script],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            # osascript 失败（如没有 Terminal 权限），降级为直接后台启动
            logger.warning(f"[login] osascript 失败（{result.stderr.strip()}），使用后台启动")
            env = os.environ.copy()
            env["COOKIES_PATH"] = cookie_path
            env.pop("XHS_PROXY", None)
            _sp.Popen([str(login_bin)], env=env,
                      stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
    else:
        # Windows / Linux：直接启动，无焦点限制
        env = os.environ.copy()
        env["COOKIES_PATH"] = cookie_path
        # 登录是本地用户操作，不传代理
        env.pop("XHS_PROXY", None)
        _sp.Popen(
            [str(login_bin)],
            env=env,
            stdout=_sp.DEVNULL,
            stderr=_sp.DEVNULL,
        )

    logger.info(f"[login] account {account_id} xiaohongshu-login 已启动，等待扫码")
    return {"ok": True, "port": row.mcp_port}


@router.get("/{account_id}/login/qr")
def login_qr(account_id: int):
    """
    获取登录二维码。
    返回 base64 图片数据，前端直接 <img src="data:image/png;base64,..."> 展示。
    """
    row = _get_or_404(account_id)
    if not mcp_manager.is_running(account_id):
        raise HTTPException(400, "mcp 进程未启动，请先调用 /login/start")

    try:
        resp = http.get(
            f"{mcp_manager.base_url(row.mcp_port)}/api/v1/login/qrcode",
            timeout=_MCP_TIMEOUT,
            proxies=_NO_PROXY,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
    except Exception as e:
        raise HTTPException(502, f"获取二维码失败：{e}")

    if data.get("is_logged_in"):
        # 已登录，不需要扫码
        _on_login_success(account_id)
        return {"already_logged_in": True}

    return {
        "img": data.get("img", ""),          # base64 图片
        "timeout": data.get("timeout", 300), # 过期秒数
        "already_logged_in": False,
    }


@router.get("/{account_id}/login/status")
def login_status(account_id: int):
    """
    轮询登录状态（前端每 2 秒调一次）。
    先检测 cookie 文件是否存在（xiaohongshu-login 写入后代表扫码成功），
    再尝试调 MCP API 获取昵称。
    """
    row = _get_or_404(account_id)

    if row.login_status == "logged_in":
        return {"logged_in": True, "nickname": row.nickname}

    # 获取保存的 cookie 路径
    c0 = database.conn()
    acc = c0.execute("SELECT cookie_file FROM account WHERE id=?", (account_id,)).fetchone()
    c0.close()
    cookie_file = acc["cookie_file"] if acc else None

    # 优先检测 cookie 文件是否已由 xiaohongshu-login 写入
    if cookie_file and Path(cookie_file).exists():
        # 尝试从 MCP 拿昵称（可选），拿不到也算成功
        nickname, xhs_user_id = "", ""
        if mcp_manager.is_running(account_id):
            try:
                resp = http.get(
                    f"{mcp_manager.base_url(row.mcp_port)}/api/v1/login/status",
                    timeout=5, proxies=_NO_PROXY,
                )
                data = resp.json().get("data", {})
                nickname = data.get("username", "")
                # login/status 响应无 user_id，不读取
            except Exception:
                pass
        _on_login_success(account_id, nickname=nickname)
        return {"logged_in": True, "nickname": nickname}

    return {"logged_in": False}


@router.delete("/{account_id}/login")
def logout(account_id: int):
    """退出登录：清除 MCP cookie 和本地 cookie 文件，标记账号为 logged_out。MCP 保持运行。"""
    row = _get_or_404(account_id)

    # 通知 mcp 清除 cookie（保持 MCP 运行，方便后续重新扫码）
    if mcp_manager.is_running(account_id):
        try:
            http.delete(
                f"{mcp_manager.base_url(row.mcp_port)}/api/v1/login/cookies",
                timeout=_MCP_TIMEOUT,
                proxies=_NO_PROXY,
            )
        except Exception as e:
            logger.warning(f"[login] 清除 mcp cookie 失败：{e}")

    # 删除本地 cookie 文件
    c = database.conn()
    acc = c.execute("SELECT cookie_file FROM account WHERE id=?", (account_id,)).fetchone()
    c.close()
    if acc and acc["cookie_file"] and os.path.exists(acc["cookie_file"]):
        os.remove(acc["cookie_file"])

    _update_account(account_id, login_status="logged_out")
    logger.info(f"[login] account {account_id} 已退出登录（MCP 保持运行）")
    return {"ok": True}


# ── mcp 进程控制 ───────────────────────────────────────────────────────────────

@router.post("/{account_id}/mcp/start")
def start_mcp(account_id: int):
    row = _get_or_404(account_id)
    c = database.conn()
    acc = c.execute("SELECT cookie_file, mcp_headless FROM account WHERE id=?", (account_id,)).fetchone()
    c.close()
    if not acc or not acc["cookie_file"]:
        raise HTTPException(400, "账号尚未登录")
    headless = bool(acc["mcp_headless"]) if acc["mcp_headless"] is not None else True
    pid = mcp_manager.start(account_id, row.mcp_port, acc["cookie_file"], None, headless=headless)
    _update_account(account_id, mcp_pid=pid)
    return {"pid": pid, "port": row.mcp_port, "headless": headless}


@router.post("/{account_id}/mcp/stop")
def stop_mcp(account_id: int):
    mcp_manager.stop(account_id)
    _update_account(account_id, mcp_pid=None)
    return {"ok": True}


@router.get("/{account_id}/mcp/status")
def mcp_status(account_id: int):
    return {"running": mcp_manager.is_running(account_id)}


@router.get("/{account_id}/mcp/logs")
def mcp_logs(account_id: int, tail: int = 100):
    """返回 MCP 进程最近 N 行日志。"""
    return {"lines": mcp_manager.get_logs(account_id, tail=tail)}


@router.post("/{account_id}/feishu/setup")
def feishu_setup(account_id: int, body: FeishuSetupIn):
    """
    用全局 App ID + Secret 自动完成该账号的飞书表格配置：
    复制模板表格 → 获取 table_id → 授权用户 → 保存到 account 表。
    幂等：若账号已有 feishu_app_token，直接返回现有配置，不重复建表。
    """
    import time as _time
    import requests as req

    app_id     = cfg.get("feishu_app_id")
    app_secret = cfg.get("feishu_app_secret")
    if not app_id or not app_secret:
        raise HTTPException(400, "请先在设置中填写飞书 App ID 和 App Secret")

    # ── 幂等检查：已配置则直接返回，避免重复建表 ──────────────────────────────
    _c0 = database.conn()
    _existing = _c0.execute(
        "SELECT feishu_app_token, feishu_table_id FROM account WHERE id=?", (account_id,)
    ).fetchone()
    _c0.close()
    if _existing and (_existing["feishu_app_token"] or "").strip():
        logger.info(f"[feishu_setup] 账号 {account_id} 表格已配置，跳过重建")
        return {
            "tenant_token_ok": True,
            "app_token": _existing["feishu_app_token"],
            "table_id":  _existing["feishu_table_id"],
            "saved": True,
            "skipped": True,
        }

    logger.info(f"[feishu_setup] 账号 {account_id} 开始建表流程")
    try:
        return _feishu_setup_inner(account_id, body, app_id, app_secret)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[feishu_setup] 账号 {account_id} 建表失败：{e}", exc_info=True)
        raise HTTPException(500, f"飞书建表失败：{e}")


def _feishu_setup_inner(account_id: int, body, app_id: str, app_secret: str) -> dict:
    import time as _time
    import requests as req

    FEISHU = "https://open.feishu.cn/open-apis"
    _TEMPLATE_APP_TOKEN = "Wf0WbW4R0a9pcJs4bm6cGEuKn7e"
    _TEMPLATE_TABLE_ID  = "tblGEBTJoqK6snYP"

    # 获取 tenant_access_token
    logger.info("[feishu_setup] 获取 tenant_access_token")
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
    result: dict = {"tenant_token_ok": True}

    # 复制模板表格
    app_token = (body.app_token or "").strip()
    table_id  = (body.table_id  or "").strip()

    if not app_token or not table_id:
        logger.info("[feishu_setup] 复制模板表格")
        try:
            copy_r = req.post(
                f"{FEISHU}/drive/v1/files/{_TEMPLATE_APP_TOKEN}/copy",
                headers=headers,
                json={"name": "RedBeacon 内容审核", "type": "bitable", "folder_token": ""},
                timeout=20,
            )
            copy_data = copy_r.json() if copy_r.status_code == 200 else {}
        except Exception as e:
            logger.warning(f"[feishu_setup] drive copy 失败，尝试 bitable copy：{e}")
            copy_data = {}

        if copy_data.get("code") == 0:
            app_token = copy_data.get("data", {}).get("file", {}).get("token") or ""
        else:
            logger.info("[feishu_setup] 第一种复制失败，尝试 bitable API")
            try:
                copy_r2 = req.post(
                    f"{FEISHU}/bitable/v1/apps/{_TEMPLATE_APP_TOKEN}/copy",
                    headers=headers,
                    json={"name": "RedBeacon 内容审核", "time_zone": "Asia/Shanghai"},
                    timeout=20,
                )
                copy_data2 = copy_r2.json() if copy_r2.status_code == 200 else {}
            except Exception as e:
                logger.warning(f"[feishu_setup] bitable copy 也失败：{e}")
                copy_data2 = {}

            if copy_data2.get("code") == 0:
                app_token = copy_data2.get("data", {}).get("app", {}).get("app_token") or ""
            else:
                logger.warning("[feishu_setup] 两种复制均失败，回退使用模板 token")
                app_token = _TEMPLATE_APP_TOKEN

        logger.info(f"[feishu_setup] app_token={app_token}，等待表格就绪")
        table_id = ""
        for attempt in range(6):   # 最多等 6 秒（之前只等 4 秒，新建表有时需要更长）
            _time.sleep(1)
            try:
                tables_r = req.get(
                    f"{FEISHU}/bitable/v1/apps/{app_token}/tables",
                    headers=headers, timeout=10,
                )
                tables = (tables_r.json().get("data", {}).get("items", [])
                          if tables_r.status_code == 200 else [])
            except Exception as e:
                logger.warning(f"[feishu_setup] 获取 table_id 第{attempt+1}次失败：{e}")
                tables = []
            if tables:
                table_id = tables[0]["table_id"]
                logger.info(f"[feishu_setup] table_id={table_id}（第{attempt+1}次）")
                break
        if not table_id:
            logger.warning("[feishu_setup] 6次重试未拿到 table_id，回退使用模板 table_id")
            table_id = _TEMPLATE_TABLE_ID

        result["app_token"] = app_token
        result["table_id"]  = table_id

    # 权限授予 + 所有者转移
    user_id = cfg.get("feishu_user_id") or ""
    if not user_id:
        _c = database.conn()
        _acc = _c.execute("SELECT feishu_user_id FROM account WHERE id=?", (account_id,)).fetchone()
        _c.close()
        if _acc:
            user_id = (_acc["feishu_user_id"] or "").strip()

    if user_id and app_token and app_token != _TEMPLATE_APP_TOKEN:
        member_type = (
            "openid"  if user_id.startswith("ou_") else
            "unionid" if user_id.startswith("on_") else
            "userid"
        )
        logger.info(f"[feishu_setup] 授权 user_id={user_id} member_type={member_type}")
        try:
            req.post(
                f"{FEISHU}/drive/v1/permissions/{app_token}/members",
                headers=headers,
                params={"type": "bitable"},
                json={"member_type": member_type, "member_id": user_id, "perm": "full_access"},
                timeout=15,
            )
        except Exception as e:
            logger.warning(f"[feishu_setup] 设置表格成员权限失败（非致命）：{e}")
        _time.sleep(0.5)
        try:
            req.post(
                f"{FEISHU}/drive/v1/permissions/{app_token}/members/transfer_owner"
                f"?type=bitable&remove_old_owner=false&stay_put=true",
                headers=headers,
                json={"member_type": member_type, "member_id": user_id,
                      "perm": "full_access", "perm_type": "set_owner", "type": "bitable"},
                timeout=15,
            )
        except Exception as e:
            logger.warning(f"[feishu_setup] 转移表格所有权失败（非致命）：{e}")

    # 保存到 account 表
    logger.info(f"[feishu_setup] 写入 DB：account_id={account_id}")
    _update_account(account_id,
        feishu_app_token=app_token or None,
        feishu_table_id=table_id or None,
    )
    result["saved"] = True
    logger.info(f"[feishu_setup] 账号 {account_id} 建表完成")
    return result


@router.post("/{account_id}/feishu/test")
def feishu_test(account_id: int):
    """测试该账号飞书表格读写 + 消息发送。"""
    import requests as req

    app_id     = cfg.get("feishu_app_id")
    app_secret = cfg.get("feishu_app_secret")
    c = database.conn()
    acc = c.execute(
        "SELECT feishu_app_token, feishu_table_id, feishu_user_id FROM account WHERE id=?",
        (account_id,),
    ).fetchone()
    c.close()

    if not acc or not acc["feishu_app_token"] or not acc["feishu_table_id"]:
        raise HTTPException(400, "请先完成飞书表格配置")
    if not app_id or not app_secret:
        raise HTTPException(400, "请先在设置中填写飞书 App ID 和 App Secret")

    app_token = acc["feishu_app_token"]
    table_id  = acc["feishu_table_id"]
    user_id   = cfg.get("feishu_user_id") or ""

    FEISHU = "https://open.feishu.cn/open-apis"
    r = req.post(
        f"{FEISHU}/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret}, timeout=15,
    )
    r.raise_for_status()
    rb = r.json()
    if rb.get("code") != 0:
        raise HTTPException(400, f"Token 获取失败：{rb.get('msg')}")
    headers = {"Authorization": f"Bearer {rb['tenant_access_token']}"}
    results: dict = {}

    write_r = req.post(
        f"{FEISHU}/bitable/v1/apps/{app_token}/tables/{table_id}/records",
        headers=headers,
        json={"fields": {"标题": "[测试] RedBeacon 连通性检测，请忽略", "状态": "未审核"}},
        timeout=15,
    )
    write_data = write_r.json() if write_r.status_code == 200 else {}
    if write_data.get("code") == 0:
        record_id = write_data["data"]["record"]["record_id"]
        results["table_write"] = "✓ 写入成功"
        del_r = req.delete(
            f"{FEISHU}/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
            headers=headers, timeout=10,
        )
        results["table_delete"] = "✓ 删除成功" if del_r.status_code == 200 else f"✗ 删除失败 {del_r.status_code}"
    else:
        results["table_write"] = f"✗ 写入失败：{write_data.get('msg') or write_r.text[:100]}"
        results["table_delete"] = "—"

    if user_id:
        id_type = (
            "open_id"  if user_id.startswith("ou_") else
            "union_id" if user_id.startswith("on_") else
            "user_id"
        )
        table_url = f"https://www.feishu.cn/base/{app_token}?table={table_id}"
        msg_r = req.post(
            f"{FEISHU}/im/v1/messages?receive_id_type={id_type}",
            headers=headers,
            json={"receive_id": user_id, "msg_type": "text",
                  "content": f'{{"text":"✅ RedBeacon 飞书连通性测试成功\\n\\n多维表格：{table_url}"}}'},
            timeout=15,
        )
        msg_data = msg_r.json() if msg_r.headers.get("content-type", "").startswith("application/json") else {}
        results["message"] = "✓ 消息发送成功" if msg_r.status_code == 200 and msg_data.get("code") == 0 \
            else f"✗ 消息发送失败：{msg_data.get('msg', msg_r.text[:80])}"
    else:
        results["message"] = "— 未配置 User ID，跳过消息测试"

    return results


@router.get("/{account_id}/login/verify")
def verify_login(account_id: int):
    """
    直接调 MCP /api/v1/login/status 验证登录状态，不走 DB 缓存。
    MCP 未运行时自动拉起（登录验证不依赖 MCP 是否已手动启动）。
    """
    row = _get_or_404(account_id)
    if not mcp_manager.is_running(account_id):
        c = database.conn()
        acc = c.execute("SELECT cookie_file, mcp_headless FROM account WHERE id=?", (account_id,)).fetchone()
        c.close()
        if not acc or not acc["cookie_file"]:
            return {"logged_in": False, "error": "尚未登录，请先扫码登录"}
        try:
            headless = cfg.get("mcp_visible", "false").lower() != "true"
            pid = mcp_manager.start(account_id, row.mcp_port, acc["cookie_file"], None, headless=headless)
            _update_account(account_id, mcp_pid=pid)
            # Windows 启动慢，等更长时间让 MCP 就绪
            import platform as _platform
            time.sleep(5 if _platform.system() == "Windows" else 2)
        except Exception as e:
            return {"logged_in": False, "error": f"MCP 启动失败：{e}"}

    # 重试 3 次（间隔 3 秒），应对 Windows 上 Chromium 启动慢的场景
    last_err = ""
    for attempt in range(3):
        try:
            resp = http.get(
                f"{mcp_manager.base_url(row.mcp_port)}/api/v1/login/status",
                timeout=_MCP_TIMEOUT,
                proxies=_NO_PROXY,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            if data.get("is_logged_in"):
                break
            last_err = ""
        except Exception as e:
            last_err = str(e)
            data = {}
        if attempt < 2:
            time.sleep(3)

    if last_err:
        return {"logged_in": False, "error": f"MCP 连接失败：{last_err}"}

    if data.get("is_logged_in"):
        nickname = data.get("username", "")
        _on_login_success(account_id, nickname=nickname)
        mcp_manager.stop(account_id)
        return {"logged_in": True, "nickname": nickname}

    # 实际未登录但 DB 标记为已登录 → 同步为 logged_out
    if row.login_status == "logged_in":
        _update_account(account_id, login_status="logged_out")
        logger.info(f"[login] account {account_id} verify 未登录，同步状态为 logged_out")
    mcp_manager.stop(account_id)
    return {"logged_in": False}


# ── 工具函数 ───────────────────────────────────────────────────────────────────

def _get_or_404(account_id: int) -> AccountOut:
    c = database.conn()
    row = c.execute("SELECT * FROM account WHERE id=?", (account_id,)).fetchone()
    c.close()
    if row is None:
        raise HTTPException(404, f"账号 {account_id} 不存在")
    return _row_to_out(row)


def _row_to_out(row) -> AccountOut:
    return AccountOut(
        id=row["id"],
        display_name=row["display_name"],
        nickname=row["nickname"],
        xhs_user_id=row["xhs_user_id"],
        login_status=row["login_status"],
        mcp_port=row["mcp_port"],
        mcp_running=mcp_manager.is_running(row["id"]),
        mcp_headless=bool(row["mcp_headless"]) if row["mcp_headless"] is not None else True,
        proxy=row["proxy"],
        last_login_check=row["last_login_check"],
        feishu_app_token=row["feishu_app_token"],
        feishu_table_id=row["feishu_table_id"],
        feishu_user_id=row["feishu_user_id"],
        auto_generate_enabled=bool(row["auto_generate_enabled"]) if row["auto_generate_enabled"] is not None else True,
        generate_schedule_json=row["generate_schedule_json"],
    )


def _update_account(account_id: int, **kwargs) -> None:
    """通用字段更新，只更新传入的 kwargs。"""
    if not kwargs:
        return
    now = datetime.now(timezone.utc).isoformat()
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [now, account_id]
    c = database.conn()
    c.execute(f"UPDATE account SET {sets}, updated_at=? WHERE id=?", vals)
    c.commit()
    c.close()


def _on_login_success(
    account_id: int,
    nickname: str = "",
    xhs_user_id: str = "",
) -> None:
    """登录成功后更新 DB。MCP 按需启动，不在此处自动拉起。"""
    now = datetime.now(timezone.utc).isoformat()
    _update_account(
        account_id,
        login_status="logged_in",
        nickname=nickname or None,
        xhs_user_id=xhs_user_id or None,
        last_login_check=now,
    )
    logger.info(f"[login] account {account_id} 登录成功，nickname={nickname}")
