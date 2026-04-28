"""routers/content.py：内容列表、状态变更、字段编辑、Job 轮询。"""
import json
import pytest


def _insert_content(account_id, status="pending_review", title="测试标题"):
    import database
    from datetime import datetime, timezone
    c = database.conn()
    c.execute(
        """INSERT INTO content_queue
           (account_id, topic, title, body, images, tags, status, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (account_id, "测试选题", title, "正文内容", "[]", "[]", status,
         datetime.now(timezone.utc).isoformat(),
         datetime.now(timezone.utc).isoformat()),
    )
    c.commit()
    cid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    c.close()
    return cid


def test_list_content_empty(client, account_id):
    r = client.get(f"/api/content/{account_id}")
    assert r.status_code == 200
    assert r.json() == []


def test_list_content(client, account_id):
    _insert_content(account_id)
    r = client.get(f"/api/content/{account_id}")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_list_content_filter_status(client, account_id):
    _insert_content(account_id, status="pending_review")
    _insert_content(account_id, status="approved")
    r = client.get(f"/api/content/{account_id}?status=pending_review")
    assert all(item["status"] == "pending_review" for item in r.json())


def test_get_content_item(client, account_id):
    cid = _insert_content(account_id, title="单条查询")
    r = client.get(f"/api/content/{account_id}/item/{cid}")
    assert r.status_code == 200
    assert r.json()["title"] == "单条查询"


def test_get_content_not_found(client, account_id):
    r = client.get(f"/api/content/{account_id}/item/9999")
    assert r.status_code == 404


def test_update_status_approve(client, account_id):
    cid = _insert_content(account_id)
    r = client.patch(f"/api/content/{account_id}/item/{cid}/status",
                     json={"status": "approved"})
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def test_update_status_reject(client, account_id):
    cid = _insert_content(account_id)
    r = client.patch(f"/api/content/{account_id}/item/{cid}/status",
                     json={"status": "rejected", "review_comment": "内容不符合要求"})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "rejected"
    assert data["review_comment"] == "内容不符合要求"


def test_update_status_invalid(client, account_id):
    cid = _insert_content(account_id)
    r = client.patch(f"/api/content/{account_id}/item/{cid}/status",
                     json={"status": "invalid_status"})
    assert r.status_code == 400


def test_edit_content_title(client, account_id):
    cid = _insert_content(account_id, title="旧标题")
    r = client.patch(f"/api/content/{account_id}/item/{cid}",
                     json={"title": "新标题"})
    assert r.status_code == 200
    assert r.json()["title"] == "新标题"


def test_edit_content_body(client, account_id):
    cid = _insert_content(account_id)
    r = client.patch(f"/api/content/{account_id}/item/{cid}",
                     json={"body": "更新后的正文"})
    assert r.status_code == 200
    assert r.json()["body"] == "更新后的正文"


def test_edit_content_tags(client, account_id):
    cid = _insert_content(account_id)
    r = client.patch(f"/api/content/{account_id}/item/{cid}",
                     json={"tags": ["职场", "干货", "成长"]})
    assert r.status_code == 200
    assert r.json()["tags"] == ["职场", "干货", "成长"]


def test_pending_endpoint(client, account_id):
    _insert_content(account_id, status="pending_review")
    _insert_content(account_id, status="approved")
    r = client.get(f"/api/content/{account_id}/pending")
    assert r.status_code == 200
    assert all(item["status"] == "pending_review" for item in r.json())


def test_feishu_url_no_config(client):
    r = client.get("/api/content/feishu-url")
    assert r.status_code == 200
    assert r.json()["url"] is None


def test_feishu_url_with_config(client, tmp_db):
    import config
    config.set("feishu_app_token", "TestToken123")
    r = client.get("/api/content/feishu-url")
    assert r.status_code == 200
    assert "TestToken123" in r.json()["url"]


def test_job_not_found(client):
    r = client.get("/api/content/jobs/nonexistentjob")
    assert r.status_code == 404


def test_trigger_generate_returns_job_id(client, account_id):
    r = client.post(f"/api/content/{account_id}/generate", json={})
    assert r.status_code == 200
    assert "job_id" in r.json()


def test_job_polling(client, account_id):
    job_id = client.post(f"/api/content/{account_id}/generate", json={}).json()["job_id"]
    r = client.get(f"/api/content/jobs/{job_id}")
    assert r.status_code == 200
    data = r.json()
    assert "step" in data
    assert "status" in data
