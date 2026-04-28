"""
RedBeacon 渲染器入口 — PyInstaller 编译为 RedBeaconRenderer 二进制。
"""
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    _bundle = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    sys.path.insert(0, str(_bundle))

# render_xhs_v2 的 CLI 入口
from render_xhs_v2 import main as render_main

if __name__ == "__main__":
    render_main()
