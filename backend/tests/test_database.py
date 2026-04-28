"""database.py：初始化、表创建、迁移幂等性。"""
import pytest


def test_init_creates_db_file(tmp_path):
    import database
    database.init_db(str(tmp_path))
    assert (tmp_path / "redbeacon.db").exists()
    database.DB_PATH = None


def test_conn_raises_before_init():
    import database
    database.DB_PATH = None
    with pytest.raises(RuntimeError):
        database.conn()


def test_tables_created(tmp_db):
    import database
    c = database.conn()
    tables = {row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    c.close()
    for expected in ("settings", "account", "strategy", "content_queue", "topic", "content_type", "image_strategy"):
        assert expected in tables


def test_migration_idempotent(tmp_db):
    """多次调用 _create_tables 不应报错。"""
    import database
    database._create_tables()
    database._create_tables()


def test_conn_row_factory(tmp_db):
    """conn() 返回的连接支持按列名访问。"""
    import database
    c = database.conn()
    c.execute("INSERT INTO settings (key, value) VALUES ('k','v')")
    c.commit()
    row = c.execute("SELECT key, value FROM settings WHERE key='k'").fetchone()
    c.close()
    assert row["key"] == "k"
    assert row["value"] == "v"
