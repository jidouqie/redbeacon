"""routers/settings.py：配置读写接口。"""


def test_get_settings_empty(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_put_setting(client):
    r = client.put("/api/settings/ai_base_url", json={"key": "ai_base_url", "value": "https://test.com/v1"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_put_then_get(client):
    client.put("/api/settings/ai_model", json={"key": "ai_model", "value": "gpt-4o"})
    settings = client.get("/api/settings").json()
    assert settings.get("ai_model") == "gpt-4o"


def test_batch_update(client):
    r = client.post("/api/settings/batch", json={
        "items": [
            {"key": "ai_base_url", "value": "https://a.com/v1"},
            {"key": "ai_model",    "value": "claude-3"},
        ]
    })
    assert r.status_code == 200
    assert r.json()["ok"] is True
    settings = client.get("/api/settings").json()
    assert settings["ai_base_url"] == "https://a.com/v1"
    assert settings["ai_model"] == "claude-3"


def test_batch_skips_sentinel(client):
    """批量接口收到哨兵值时不应覆盖原有值。"""
    import config
    config.set("ai_api_key", "real_key")
    client.post("/api/settings/batch", json={
        "items": [{"key": "ai_api_key", "value": "__SET__"}]
    })
    assert config.get("ai_api_key") == "real_key"


def test_encrypted_field_returns_sentinel(client):
    import config
    config.set("ai_api_key", "sk-abc")
    settings = client.get("/api/settings").json()
    assert settings.get("ai_api_key") == "__SET__"
