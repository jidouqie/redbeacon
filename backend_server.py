"""
RedBeacon 后端服务入口 — PyInstaller 编译为 RedBeaconServer 二进制。
所有 backend/ 源码打入此二进制，交付包中不含任何 .py 文件。
"""
import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    _bundle = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    sys.path.insert(0, str(_bundle))

# 显式引入所有后端模块，让 PyInstaller 能完整打包依赖树
import main  # noqa: F401
import database  # noqa: F401
import config  # noqa: F401
import scheduler  # noqa: F401
import routers.account  # noqa: F401
import routers.content  # noqa: F401
import routers.strategy  # noqa: F401
import routers.settings  # noqa: F401
import routers.topics  # noqa: F401
import routers.automation  # noqa: F401
import routers.debug  # noqa: F401
import services.mcp_manager  # noqa: F401
import services.feishu_api  # noqa: F401
import services.image_gen  # noqa: F401
import services.proxy_service  # noqa: F401
import tasks.generate  # noqa: F401
import tasks.publish  # noqa: F401
import tasks.feishu_sync  # noqa: F401
import utils.logger  # noqa: F401
import utils.crypto  # noqa: F401
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("REDBEACON_PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
