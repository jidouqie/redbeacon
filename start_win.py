"""Windows startup helper — spawns backend + frontend and keeps running."""
import subprocess
import sys
import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()


def main():
    env = os.environ.copy()
    env.setdefault("REDBEACON_DATA_DIR", str(SCRIPT_DIR / "data"))
    env.setdefault("REDBEACON_LOG_DIR",  str(SCRIPT_DIR / "logs"))
    env.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(SCRIPT_DIR / "data" / "playwright"))

    print("[RedBeacon] 启动后端 :8000 ...", flush=True)
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app",
         "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(SCRIPT_DIR / "backend"),
        env=env,
    )

    print("[RedBeacon] 启动前端 :3000 ...", flush=True)
    next_cmd = SCRIPT_DIR / "frontend" / "node_modules" / ".bin" / "next.cmd"
    if not next_cmd.exists():
        next_cmd = SCRIPT_DIR / "frontend" / "node_modules" / ".bin" / "next"
    frontend = subprocess.Popen(
        [str(next_cmd), "dev", "--webpack", "--port", "3000"],
        cwd=str(SCRIPT_DIR / "frontend"),
        env=env,
    )

    print("[RedBeacon] 已启动：", flush=True)
    print("  后端  http://127.0.0.1:8000", flush=True)
    print("  前端  http://127.0.0.1:3000", flush=True)
    print("  API文档  http://127.0.0.1:8000/docs", flush=True)

    try:
        backend.wait()
        frontend.wait()
    except KeyboardInterrupt:
        backend.terminate()
        frontend.terminate()
    finally:
        try:
            backend.kill()
        except Exception:
            pass
        try:
            frontend.kill()
        except Exception:
            pass


if __name__ == "__main__":
    main()
