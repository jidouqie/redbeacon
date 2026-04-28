"""config.py：加密字段、哨兵值、普通读写。"""
import pytest


def test_set_and_get_plain(tmp_db):
    import config
    config.set("some_key", "hello")
    assert config.get("some_key") == "hello"


def test_get_default_when_missing(tmp_db):
    import config
    assert config.get("nonexistent_key") == ""
    assert config.get("nonexistent_key", "fallback") == "fallback"


def test_overwrite_value(tmp_db):
    import config
    config.set("k", "v1")
    config.set("k", "v2")
    assert config.get("k") == "v2"


def test_encrypted_field_stored_encrypted(tmp_db):
    """加密字段写入后，数据库中存的不是明文。"""
    import config, database
    config.set("ai_api_key", "sk-secret")
    c = database.conn()
    row = c.execute("SELECT value, is_encrypted FROM settings WHERE key='ai_api_key'").fetchone()
    c.close()
    assert row["is_encrypted"] == 1
    assert row["value"] != "sk-secret"      # 存储的是密文
    assert config.get("ai_api_key") == "sk-secret"   # 读回来是明文


def test_encrypted_field_feishu_secret(tmp_db):
    import config
    config.set("feishu_app_secret", "my_secret")
    assert config.get("feishu_app_secret") == "my_secret"


def test_get_all_public_sentinel(tmp_db):
    """已设置的加密字段在 get_all_public 中返回 '__SET__'。"""
    import config
    config.set("ai_api_key", "sk-123")
    pub = config.get_all_public()
    assert pub["ai_api_key"] == config._SENTINEL


def test_get_all_public_plain_value(tmp_db):
    import config
    config.set("ai_base_url", "https://api.example.com/v1")
    pub = config.get_all_public()
    assert pub["ai_base_url"] == "https://api.example.com/v1"


def test_empty_encrypted_not_sentinel(tmp_db):
    """加密字段为空时 get_all_public 返回空字符串，不是哨兵值。"""
    import config
    config.set("ai_api_key", "")
    pub = config.get_all_public()
    assert pub.get("ai_api_key", "") == ""
