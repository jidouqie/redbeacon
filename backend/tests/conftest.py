"""共享 fixtures：临时数据库 + FastAPI TestClient（隔离 lifespan 副作用）。"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture()
def tmp_db(tmp_path):
    """每个测试用独立临时 SQLite 数据库。"""
    import database
    database.init_db(str(tmp_path))
    yield tmp_path
    database.DB_PATH = None


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """
    FastAPI TestClient。
    - 将 DATA_DIR / LOG_DIR 重定向到临时目录
    - mock _auto_start_mcp 避免真实 MCP 进程启动
    """
    import database
    database.init_db(str(tmp_path))

    import main
    monkeypatch.setattr(main, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(main, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(main, "_auto_start_mcp", lambda: None)

    import scheduler as sched
    monkeypatch.setattr(sched, "start", lambda: None)
    monkeypatch.setattr(sched, "stop", lambda: None)

    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c

    database.DB_PATH = None


@pytest.fixture()
def account_id(client):
    """插入 id=1 的默认账号。"""
    import database
    c = database.conn()
    c.execute(
        "INSERT OR IGNORE INTO account (id, nickname, login_status, mcp_port)"
        " VALUES (1,'测试账号','logged_in',18060)"
    )
    c.commit()
    c.close()
    return 1
