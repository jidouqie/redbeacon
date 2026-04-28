"""services/mcp_manager.py：base_url、is_running、_mcp_binary 路径解析。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_base_url():
    from services.mcp_manager import base_url
    assert base_url(18060) == "http://127.0.0.1:18060"
    assert base_url(9000) == "http://127.0.0.1:9000"


def test_is_running_false_for_unknown(tmp_db):
    from services.mcp_manager import is_running
    assert is_running(999) is False


def test_mcp_binary_reads_db_path(tmp_db, monkeypatch):
    """数据库中配置了有效路径时，_mcp_binary 应返回该路径。"""
    import config
    # 使用 sys.executable（Python 自身）作为"存在的可执行文件"
    config.set("mcp_binary_path", sys.executable)
    from services import mcp_manager
    import importlib
    importlib.reload(mcp_manager)   # 让模块重新读取配置
    path = mcp_manager._mcp_binary()
    assert str(path) == sys.executable


def test_mcp_binary_raises_when_path_not_exist(tmp_db):
    import config
    config.set("mcp_binary_path", "/nonexistent/path/mcp")
    from services import mcp_manager
    import importlib
    importlib.reload(mcp_manager)
    with pytest.raises(FileNotFoundError):
        mcp_manager._mcp_binary()


import pytest
