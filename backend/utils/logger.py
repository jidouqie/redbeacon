import io
import logging
import sys
from pathlib import Path

_logger: logging.Logger | None = None


def init_logger(log_dir: str, level: int = logging.INFO) -> None:
    global _logger
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    handler_file = logging.FileHandler(
        Path(log_dir) / "redbeacon.log", encoding="utf-8"
    )
    # Force UTF-8 on Windows console to prevent GBK UnicodeEncodeError
    if sys.platform == "win32":
        utf8_stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
        )
        handler_console = logging.StreamHandler(utf8_stdout)
    else:
        handler_console = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler_file.setFormatter(fmt)
    handler_console.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler_file)
    root.addHandler(handler_console)
    _logger = logging.getLogger("redbeacon")


def get_logger(name: str = "redbeacon") -> logging.Logger:
    return logging.getLogger(name)
