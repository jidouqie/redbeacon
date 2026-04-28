"""routers/strategy.py：账号策略、提示词、图片策略。"""
import json


def test_get_strategy_no_data(client, account_id):
    r = client.get(f"/api/strategy/{account_id}")
    assert r.status_code in (200, 404)


def test_upsert_and_get_strategy(client, account_id):
    payload = {"niche": "职场成长", "target_audience": "25-35岁职场人"}
    r = client.patch(f"/api/strategy/{account_id}", json=payload)
    assert r.status_code == 200
    data = client.get(f"/api/strategy/{account_id}").json()
    assert data["niche"] == "职场成长"


def test_edit_strategy_fields(client, account_id):
    client.patch(f"/api/strategy/{account_id}", json={"niche": "健康生活"})
    client.patch(f"/api/strategy/{account_id}", json={"tone": "轻松活泼"})
    data = client.get(f"/api/strategy/{account_id}").json()
    strategy = json.loads(data["data"])
    assert strategy.get("tone") == "轻松活泼"


def test_get_image_strategy_default(client, account_id):
    r = client.get(f"/api/strategy/{account_id}/image")
    assert r.status_code == 200
    data = r.json()
    assert "mode" in data
    assert "card_theme" in data


def test_update_image_strategy(client, account_id):
    payload = {
        "mode": "both",
        "prompt_template": "生成{niche}风格的图片",
        "card_theme": "mint",
        "reference_images": [],
        "ai_model": "gemini-flash",
    }
    r = client.put(f"/api/strategy/{account_id}/image", json=payload)
    assert r.status_code == 200
    data = client.get(f"/api/strategy/{account_id}/image").json()
    assert data["mode"] == "both"
    assert data["card_theme"] == "mint"
    assert data["ai_model"] == "gemini-flash"


def test_add_prompt(client, account_id):
    r = client.post(f"/api/strategy/{account_id}/prompts", json={
        "type": "copy",
        "name": "主提示词",
        "prompt_text": "写一篇关于{topic}的小红书文案",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "主提示词"


def test_list_prompts(client, account_id):
    client.post(f"/api/strategy/{account_id}/prompts", json={
        "type": "copy", "name": "P1", "prompt_text": "模板1",
    })
    r = client.get(f"/api/strategy/{account_id}/prompts")
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_update_prompt(client, account_id):
    pid = client.post(f"/api/strategy/{account_id}/prompts", json={
        "type": "copy", "name": "P1", "prompt_text": "旧模板",
    }).json()["id"]
    r = client.put(f"/api/strategy/{account_id}/prompts/{pid}", json={
        "prompt_text": "新模板",
    })
    assert r.status_code == 200
    assert r.json()["prompt_text"] == "新模板"
