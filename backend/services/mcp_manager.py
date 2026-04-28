"""
xiaohongshu-mcp 子进程管理。
每个账号独占一个端口和一个进程，由 FastAPI 启动时按需拉起，
账号登出或删除时关闭对应进程。
"""
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

from utils.logger import get_logger

logger = get_logger("mcp_manager")

# MCP 二进制路径：优先读数据库配置，再看环境变量，最后查打包目录

def _platform_suffix() -> str:
    """返回当前平台对应的二进制后缀，如 darwin-arm64 / linux-amd64 / windows-amd64。"""
    import platform as _platform
    _os = {"darwin": "darwin", "win32": "windows"}.get(sys.platform, "linux")
    _machine = _platform.machine().lower()
    _arch = "arm64" if _machine in ("arm64", "aarch64") else "amd64"
    return f"{_os}-{_arch}"


def _find_binary(prefix: str) -> Path:
    """
    在工具目录中查找以 prefix 开头的二进制文件。
    优先匹配当前平台后缀（如 xiaohongshu-login-darwin-arm64），
    找不到再退化为任意匹配的文件。
    """
    d = _tools_dir()
    suffix = _platform_suffix()
    is_win = sys.platform == "win32"

    # 1. 精确匹配当前平台
    candidates = [
        d / f"{prefix}-{suffix}.exe",
        d / f"{prefix}-{suffix}",
    ] if is_win else [
        d / f"{prefix}-{suffix}",
        d / f"{prefix}-{suffix}.exe",
    ]
    for p in candidates:
        if p.exists():
            return p

    # 2. 兜底：取目录内任意以 prefix 开头的可执行文件（字母序第一个）
    matches = sorted(d.glob(f"{prefix}*"))
    for p in matches:
        if p.is_file() and not p.name.endswith((".md", ".txt")):
            return p

    raise FileNotFoundError(
        f"在 {d} 中找不到 {prefix}（当前平台：{suffix}）。"
        "请在「设置 → MCP 配置」中选择正确的工具目录。"
    )


def _login_binary() -> Path:
    return _find_binary("xiaohongshu-login")


def _tools_dir() -> Path:
    """返回工具目录：优先读 mcp_tools_dir 设置，其次 tools/ 默认目录，其次 MCP_BINARY 所在目录。"""
    import config as _cfg
    # 1. 用户在设置页指定的目录
    db_dir = _cfg.get("mcp_tools_dir", "").strip()
    if db_dir:
        p = Path(db_dir)
        if p.is_dir():
            return p
        raise FileNotFoundError(f"设置中的工具目录不存在：{db_dir}")
    # 2. 默认 tools/ 目录（redbeacon/tools/）
    project_root = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent.parent))
    default = project_root / "tools"
    if default.is_dir():
        return default
    # 3. MCP_BINARY 环境变量所在目录（只要目录存在就用，二进制名可能带平台后缀）
    env_bin = Path(os.environ.get("MCP_BINARY", ""))
    if env_bin.parent.is_dir():
        return env_bin.parent
    return project_root


def _mcp_binary() -> Path:
    return _find_binary("xiaohongshu-mcp")


# 运行中的进程表：account_id -> subprocess.Popen
_processes: dict[int, subprocess.Popen] = {}

# 日志环形缓冲：account_id -> deque(最多 300 行)
_LOG_MAX = 300
_log_buffers: dict[int, deque] = {}
_log_lock = threading.Lock()


def get_logs(account_id: int, tail: int = 100) -> list[str]:
    with _log_lock:
        buf = _log_buffers.get(account_id, deque())
        lines = list(buf)
    return lines[-tail:] if tail < len(lines) else lines


def _start_log_reader(account_id: int, proc: subprocess.Popen) -> None:
    with _log_lock:
        _log_buffers[account_id] = deque(maxlen=_LOG_MAX)

    def _read():
        try:
            for line in proc.stdout:
                line = line.rstrip("\n")
                with _log_lock:
                    _log_buffers[account_id].append(line)
        except Exception:
            pass

    t = threading.Thread(target=_read, daemon=True)
    t.start()


def start(
    account_id: int,
    port: int,
    cookie_file: str,
    proxy: str | None = None,
    headless: bool = True,
) -> int:
    """
    启动指定账号的 mcp 进程。
    返回进程 PID；若已在运行且模式一致则直接返回已有 PID。
    headless=False 时浏览器窗口可见，供手动操作。
    """
    if account_id in _processes:
        proc = _processes[account_id]
        if proc.poll() is None:
            logger.info(f"[mcp] account {account_id} 已在运行，PID={proc.pid}")
            return proc.pid
        else:
            logger.warning(f"[mcp] account {account_id} 进程已退出，重新启动")
            del _processes[account_id]

    # 启动前检查端口是否被残留进程占用
    if _port_in_use(port):
        logger.warning(f"[mcp] 端口 {port} 已被占用，清理残留进程…")
        _kill_port(port)
        if _port_in_use(port):
            raise RuntimeError(f"端口 {port} 仍被占用，无法启动 MCP。请手动检查并释放该端口。")

    binary = _mcp_binary()
    cmd = [str(binary), "-port", f":{port}", f"-headless={'true' if headless else 'false'}"]

    env = os.environ.copy()
    if cookie_file:
        env["COOKIES_PATH"] = cookie_file
    if proxy:
        env["XHS_PROXY"] = proxy

    logger.info(f"[mcp] 启动 account {account_id}：{' '.join(cmd)}  COOKIES_PATH={cookie_file}")
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    _processes[account_id] = proc
    _start_log_reader(account_id, proc)
    logger.info(f"[mcp] account {account_id} 已启动，PID={proc.pid}")
    return proc.pid


def stop(account_id: int) -> None:
    """关闭指定账号的 mcp 进程。"""
    proc = _processes.pop(account_id, None)
    if proc is None:
        return
    if proc.poll() is None:
        try:
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    logger.info(f"[mcp] account {account_id} 进程已停止")


def stop_all() -> None:
    """程序退出时关闭所有 mcp 进程。"""
    for account_id in list(_processes.keys()):
        stop(account_id)


def is_running(account_id: int) -> bool:
    proc = _processes.get(account_id)
    return proc is not None and proc.poll() is None


def base_url(port: int) -> str:
    """返回 mcp REST API 的基础地址。"""
    return f"http://127.0.0.1:{port}"


def _port_in_use(port: int) -> bool:
    """检查端口是否已被占用。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _kill_port(port: int) -> None:
    """找到占用端口的进程并 kill，等待端口释放。"""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True,
        )
        pids = result.stdout.strip().split()
        for pid_str in pids:
            try:
                pid = int(pid_str)
                os.kill(pid, signal.SIGTERM)
                logger.warning(f"[mcp] 端口 {port} 已被 PID={pid} 占用，已发送 SIGTERM")
            except (ValueError, ProcessLookupError):
                pass
        # 等端口释放，最多 3 秒
        for _ in range(6):
            time.sleep(0.5)
            if not _port_in_use(port):
                break
        else:
            # SIGTERM 无效时强制 kill
            for pid_str in pids:
                try:
                    os.kill(int(pid_str), signal.SIGKILL)
                except Exception:
                    pass
            time.sleep(0.5)
    except FileNotFoundError:
        # lsof 不存在（Windows），忽略
        pass
