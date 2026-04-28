"""
RedBeacon Launcher
Start/stop the project, view service status and logs.
Requires: pip install customtkinter
"""
APP_VERSION = "0.0.1"
import customtkinter as ctk
import subprocess
import threading
import socket
import webbrowser
import os
import sys
import signal
import platform
from pathlib import Path

# -- Project root path --------------------------------------------------------

IS_WINDOWS = platform.system() == "Windows"
IS_MAC     = platform.system() == "Darwin"

if getattr(sys, "frozen", False):
    # Running as a PyInstaller bundle
    if IS_MAC:
        # Executable lives at: RedBeacon.app/Contents/MacOS/RedBeacon
        # Project root is three levels up: MacOS -> Contents -> RedBeacon.app -> project
        SCRIPT_DIR = Path(sys.executable).parent.parent.parent.parent
    else:
        # Windows / Linux: executable sits directly in the project root
        SCRIPT_DIR = Path(sys.executable).parent
else:
    SCRIPT_DIR = Path(__file__).parent.resolve()

BACKEND_PORT  = 8000
BACKEND_URL   = f"http://localhost:{BACKEND_PORT}"
FRONTEND_URL  = BACKEND_URL  # 前端由后端静态托管，同端口

# -- Colors -------------------------------------------------------------------

COLOR_GREEN  = "#22c55e"
COLOR_RED    = "#ef4444"
COLOR_YELLOW = "#fbbf24"
COLOR_MUTED  = "#6b7280"
COLOR_BG     = "#0f1117"
COLOR_SURFACE = "#1a1d27"
COLOR_BORDER = "#2d3148"
COLOR_ACCENT = "#6366f1"

# -- Port probe ---------------------------------------------------------------

def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


# -- Main window --------------------------------------------------------------

class LauncherApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self._proc: subprocess.Popen | None = None
        self._stopping = False
        self._was_up   = False  # tracks whether both services were up in the last poll

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("RedBeacon")
        self.geometry("420x560")
        self.resizable(False, False)
        self.configure(fg_color=COLOR_BG)

        if IS_MAC:
            self.createcommand("tk::mac::Quit", self._on_close)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._poll_status()

        # Auto-start if launched with --start flag (e.g. triggered by skill)
        if "--start" in sys.argv:
            self.after(500, self._start)

    # -- UI -------------------------------------------------------------------

    def _build_ui(self):
        # Title bar
        title_frame = ctk.CTkFrame(self, fg_color=COLOR_SURFACE, corner_radius=0, height=52)
        title_frame.pack(fill="x")
        title_frame.pack_propagate(False)
        ctk.CTkLabel(title_frame, text="RedBeacon", font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ffffff").pack(side="left", padx=18, pady=14)
        ctk.CTkLabel(title_frame, text="\u5c0f\u7ea2\u4e66 AI \u8fd0\u8425\u5e73\u53f0",
                     font=ctk.CTkFont(size=11), text_color=COLOR_MUTED).pack(side="left")

        # Status card
        status_frame = ctk.CTkFrame(self, fg_color=COLOR_SURFACE, corner_radius=10)
        status_frame.pack(fill="x", padx=16, pady=(14, 0))

        ctk.CTkLabel(status_frame, text="\u670d\u52a1\u72b6\u6001",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=COLOR_MUTED).pack(anchor="w", padx=14, pady=(12, 6))

        # Backend status row
        backend_row = ctk.CTkFrame(status_frame, fg_color="transparent")
        backend_row.pack(fill="x", padx=14, pady=(0, 6))
        self._dot_backend = ctk.CTkLabel(backend_row, text="\u25cf", width=16,
                                         font=ctk.CTkFont(size=14), text_color=COLOR_RED)
        self._dot_backend.pack(side="left")
        ctk.CTkLabel(backend_row, text="\u540e\u7aef",
                     font=ctk.CTkFont(size=13), text_color="#e2e8f0").pack(side="left", padx=(6, 0))
        self._label_backend = ctk.CTkLabel(backend_row, text="\u5df2\u505c\u6b62",
                                           font=ctk.CTkFont(size=12), text_color=COLOR_MUTED)
        self._label_backend.pack(side="right")

        # Frontend status row
        frontend_row = ctk.CTkFrame(status_frame, fg_color="transparent")
        frontend_row.pack(fill="x", padx=14, pady=(0, 12))
        self._dot_frontend = ctk.CTkLabel(frontend_row, text="\u25cf", width=16,
                                          font=ctk.CTkFont(size=14), text_color=COLOR_RED)
        self._dot_frontend.pack(side="left")
        ctk.CTkLabel(frontend_row, text="\u524d\u7aef",
                     font=ctk.CTkFont(size=13), text_color="#e2e8f0").pack(side="left", padx=(6, 0))
        self._label_frontend = ctk.CTkLabel(frontend_row, text="\u5df2\u505c\u6b62",
                                            font=ctk.CTkFont(size=12), text_color=COLOR_MUTED)
        self._label_frontend.pack(side="right")

        # Action buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=12)

        self._btn_start = ctk.CTkButton(
            btn_frame, text="\u542f\u52a8\u9879\u76ee", height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLOR_ACCENT, hover_color="#4f46e5",
            command=self._start)
        self._btn_start.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self._btn_stop = ctk.CTkButton(
            btn_frame, text="\u505c\u6b62", height=40,
            font=ctk.CTkFont(size=13),
            fg_color=COLOR_SURFACE, hover_color="#2d3148",
            text_color="#e2e8f0", border_width=1, border_color=COLOR_BORDER,
            command=self._stop, state="disabled")
        self._btn_stop.pack(side="left", expand=True, fill="x", padx=(6, 0))

        self._btn_open = ctk.CTkButton(
            self, text="\u6253\u5f00\u7ba1\u7406\u754c\u9762", height=40,
            font=ctk.CTkFont(size=13),
            fg_color=COLOR_SURFACE, hover_color="#2d3148",
            text_color="#e2e8f0", border_width=1, border_color=COLOR_BORDER,
            command=self._open_ui, state="disabled")
        self._btn_open.pack(fill="x", padx=16, pady=(0, 12))

        # Log area
        log_header = ctk.CTkFrame(self, fg_color="transparent")
        log_header.pack(fill="x", padx=16, pady=(0, 4))
        ctk.CTkLabel(log_header, text="\u8fd0\u884c\u65e5\u5fd7",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=COLOR_MUTED).pack(side="left")
        ctk.CTkButton(log_header, text="\u6e05\u5c4f", width=44, height=22,
                      font=ctk.CTkFont(size=11),
                      fg_color="transparent", hover_color=COLOR_SURFACE,
                      text_color=COLOR_MUTED, border_width=1, border_color=COLOR_BORDER,
                      command=self._clear_log).pack(side="right")

        self._log_box = ctk.CTkTextbox(
            self, font=ctk.CTkFont(family="Menlo" if IS_MAC else "Consolas", size=11),
            fg_color=COLOR_SURFACE, text_color="#8b949e",
            corner_radius=10, wrap="word", state="disabled")
        self._log_box.pack(fill="both", expand=True, padx=16, pady=(0, 14))

    # -- Actions --------------------------------------------------------------

    def _start(self):
        if self._proc and self._proc.poll() is None:
            return
        self._stopping = False
        self._btn_start.configure(state="disabled", text="\u542f\u52a8\u4e2d\u2026")
        self._btn_stop.configure(state="normal")
        self._log("\u6b63\u5728\u542f\u52a8 RedBeacon\u2026")

        def run():
            env = os.environ.copy()
            env["REDBEACON_DATA_DIR"] = str(SCRIPT_DIR / "data")
            env["REDBEACON_LOG_DIR"]  = str(SCRIPT_DIR / "logs")
            env["PLAYWRIGHT_BROWSERS_PATH"] = str(SCRIPT_DIR / "data" / "playwright")
            mcp_name = "xiaohongshu-mcp.exe" if IS_WINDOWS else "xiaohongshu-mcp"
            env["MCP_BINARY"] = str(SCRIPT_DIR / "tools" / mcp_name)

            if IS_WINDOWS:
                server_bin = SCRIPT_DIR / "RedBeaconServer.exe"
                if server_bin.exists():
                    cmd = [str(server_bin)]
                else:
                    cmd = [str(SCRIPT_DIR / "start.bat")]
                self._proc = subprocess.Popen(
                    cmd, cwd=str(SCRIPT_DIR), env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                )
            else:
                server_bin = SCRIPT_DIR / "RedBeaconServer"
                if server_bin.exists():
                    # 生产包：直接启动编译好的二进制
                    cmd = [str(server_bin)]
                else:
                    # 开发环境：通过 start.sh 启动
                    cmd = ["bash", str(SCRIPT_DIR / "start.sh")]
                self._proc = subprocess.Popen(
                    cmd, cwd=str(SCRIPT_DIR), env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    preexec_fn=os.setsid,
                )

            for line in self._proc.stdout:
                if self._stopping:
                    break
                self._log(line.rstrip())

            if not self._stopping:
                self._log("\u26a0 \u8fdb\u7a0b\u5df2\u9000\u51fa")
                self.after(0, lambda: self._btn_start.configure(
                    state="normal", text="\u542f\u52a8\u9879\u76ee"))

        threading.Thread(target=run, daemon=True).start()

    def _reset_start_button(self):
        self._btn_start.configure(state="normal", text="\u542f\u52a8\u9879\u76ee")
        self._btn_stop.configure(state="disabled")

    def _stop(self):
        self._stopping = True
        self._log("\u6b63\u5728\u505c\u6b62\u670d\u52a1\u2026")
        self._btn_stop.configure(state="disabled")
        self._btn_start.configure(state="disabled")

        def do_stop():
            import time

            # Send termination signal
            if IS_WINDOWS:
                if self._proc:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(self._proc.pid)],
                                   capture_output=True)
            else:
                if self._proc:
                    try:
                        os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                # \u515c\u5e95\uff1a\u6309\u540d\u79f0\u6740\u6389\u53ef\u80fd\u6b8b\u7559\u7684\u8fdb\u7a0b
                subprocess.run(["pkill", "-f", "RedBeaconServer"], capture_output=True)
                subprocess.run(["pkill", "-f", "uvicorn main:app"], capture_output=True)

            self._proc = None

            # Wait for port to be released (up to 10 seconds)
            for _ in range(20):
                time.sleep(0.5)
                if not port_open(BACKEND_PORT):
                    break
            else:
                # Timeout: force kill by port
                self._log("\u7aef\u53e3\u672a\u91ca\u653e\uff0c\u5f3a\u5236\u7ec8\u6b62\u2026")
                if IS_WINDOWS:
                    result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
                    for line in result.stdout.splitlines():
                        if f":{BACKEND_PORT} " in line and ("LISTENING" in line or "ESTABLISHED" in line):
                            parts = line.split()
                            if parts:
                                try:
                                    subprocess.run(["taskkill", "/F", "/PID", parts[-1]], capture_output=True)
                                except Exception:
                                    pass
                else:
                    result = subprocess.run(["lsof", "-ti", f":{BACKEND_PORT}"], capture_output=True, text=True)
                    for pid_str in result.stdout.split():
                        try:
                            os.kill(int(pid_str), signal.SIGKILL)
                        except (ProcessLookupError, ValueError):
                            pass

            self._stopping = False
            self._was_up   = False
            self._log("\u2713 \u670d\u52a1\u5df2\u505c\u6b62")
            self.after(0, self._reset_start_button)

        threading.Thread(target=do_stop, daemon=True).start()

    def _open_ui(self):
        webbrowser.open(FRONTEND_URL)

    def _on_close(self):
        if self._proc and self._proc.poll() is None:
            self._stop()
        self.after(800, self.destroy)

    # -- Logging --------------------------------------------------------------

    def _log(self, text: str):
        def _append():
            self._log_box.configure(state="normal")
            self._log_box.insert("end", text + "\n")
            self._log_box.see("end")
            self._log_box.configure(state="disabled")
        self.after(0, _append)

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    # -- Status polling -------------------------------------------------------

    def _poll_status(self):
        backend_up = port_open(BACKEND_PORT)

        # Update status dots \u2014 frontend is now served by backend on same port
        self._dot_backend.configure(text_color=COLOR_GREEN if backend_up else COLOR_RED)
        self._label_backend.configure(
            text=f"\u8fd0\u884c\u4e2d :{BACKEND_PORT}" if backend_up else "\u5df2\u505c\u6b62",
            text_color=COLOR_GREEN if backend_up else COLOR_MUTED)

        self._dot_frontend.configure(text_color=COLOR_GREEN if backend_up else COLOR_RED)
        self._label_frontend.configure(
            text="\u5185\u7f6e\u9759\u6001\u6258\u7ba1" if backend_up else "\u5df2\u505c\u6b62",
            text_color=COLOR_GREEN if backend_up else COLOR_MUTED)

        self._btn_open.configure(state="normal" if backend_up else "disabled")

        # Update start / stop button states
        proc_running = self._proc is not None and self._proc.poll() is None
        if self._stopping:
            pass  # buttons managed by _stop() during shutdown
        elif backend_up:
            self._btn_start.configure(state="disabled", text="\u8fd0\u884c\u4e2d")
            self._btn_stop.configure(state="normal")
            if not self._was_up:
                self._log("\u2713 RedBeacon \u5df2\u5c31\u7eea")
                self._log(f"  Web UI\uff1a{FRONTEND_URL}")
                self._log(f"  API \u6587\u6863\uff1a{BACKEND_URL}/docs")
                self._was_up = True
        elif proc_running:
            pass
        else:
            self._btn_start.configure(state="normal", text="\u542f\u52a8\u9879\u76ee")
            self._btn_stop.configure(state="disabled")
            self._was_up = False

        self.after(2000, self._poll_status)


# -- Singleton lock -----------------------------------------------------------

_lock_fd = None  # keep reference to prevent GC from closing the fd

def _acquire_singleton() -> bool:
    """Return True if this is the only running instance, False otherwise."""
    global _lock_fd
    lock_path = SCRIPT_DIR / "logs" / "launcher.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if IS_WINDOWS:
        import msvcrt
        try:
            _lock_fd = open(lock_path, "w")
            msvcrt.locking(_lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
            _lock_fd.write(str(os.getpid()))
            _lock_fd.flush()
            return True
        except OSError:
            return False
    else:
        import fcntl
        try:
            _lock_fd = open(lock_path, "w")
            fcntl.lockf(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _lock_fd.write(str(os.getpid()))
            _lock_fd.flush()
            return True
        except OSError:
            return False


# -- Entry point --------------------------------------------------------------

if __name__ == "__main__":
    if not _acquire_singleton():
        # Another launcher is already running — just exit silently.
        # On macOS the OS-level 'open' handler already focuses the existing window.
        sys.exit(0)

    try:
        import customtkinter
    except ImportError:
        print("customtkinter not found, installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "customtkinter"], check=True)
        import customtkinter as ctk

    app = LauncherApp()
    app.mainloop()
