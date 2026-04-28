"""routers/topics.py：选题库 CRUD、统计、批量导入、原子消费。"""
import pytest


def test_list_topics_empty(client, account_id):
    r = client.get(f"/api/topics/{account_id}")
    assert r.status_code == 200
    assert r.json() == []


def test_create_topic(client, account_id):
    r = client.post(f"/api/topics/{account_id}", json={"content_type": "干货", "content": "如何高效学习"})
    assert r.status_code in (200, 201)
    data = r.json()
    assert data["content"] == "如何高效学习"
    assert data["is_used"] is False


def test_delete_topic(client, account_id):
    tid = client.post(f"/api/topics/{account_id}", json={"content_type": "干货", "content": "to delete"}).json()["id"]
    r = client.delete(f"/api/topics/{account_id}/{tid}")
    assert r.status_code == 204
    topics = client.get(f"/api/topics/{account_id}").json()
    assert all(t["id"] != tid for t in topics)


def test_stats_empty(client, account_id):
    r = client.get(f"/api/topics/{account_id}/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["unused"] == 0


def test_stats_after_create(client, account_id):
    client.post(f"/api/topics/{account_id}", json={"content_type": "干货", "content": "选题A"})
    client.post(f"/api/topics/{account_id}", json={"content_type": "干货", "content": "选题B"})
    data = client.get(f"/api/topics/{account_id}/stats").json()
    assert data["total"] == 2
    assert data["unused"] == 2
    assert data["used"] == 0


def test_batch_import(client, account_id):
    r = client.post(f"/api/topics/{account_id}/batch", json={
        "content_type": "干货",
        "text": "选题一\n选题二\n选题三",
    })
    assert r.status_code in (200, 201)
    assert r.json()["inserted"] == 3
    assert client.get(f"/api/topics/{account_id}/stats").json()["total"] == 3


def test_batch_import_dedup(client, account_id):
    client.post(f"/api/topics/{account_id}", json={"content_type": "干货", "content": "重复选题"})
    r = client.post(f"/api/topics/{account_id}/batch", json={
        "content_type": "干货",
        "text": "重复选题\n新选题",
    })
    assert r.json()["inserted"] == 1   # 重复的不插入


def test_reset_topic(client, account_id):
    tid = client.post(f"/api/topics/{account_id}", json={"content_type": "干货", "content": "可重置"}).json()["id"]
    # 手动标记为已使用
    import database
    c = database.conn()
    c.execute("UPDATE topic SET is_used=1 WHERE id=?", (tid,))
    c.commit()
    c.close()
    r = client.post(f"/api/topics/{account_id}/{tid}/reset")
    assert r.status_code == 200
    topics = client.get(f"/api/topics/{account_id}").json()
    t = next(x for x in topics if x["id"] == tid)
    assert t["is_used"] is False


def test_reset_all(client, account_id):
    for i in range(3):
        client.post(f"/api/topics/{account_id}", json={"content_type": "干货", "content": f"t{i}"})
    import database
    c = database.conn()
    c.execute("UPDATE topic SET is_used=1 WHERE account_id=?", (account_id,))
    c.commit()
    c.close()
    client.post(f"/api/topics/{account_id}/reset-all")
    stats = client.get(f"/api/topics/{account_id}/stats").json()
    assert stats["unused"] == 3


def test_pop_next_topic(account_id, tmp_db):
    """pop_next_topic 原子消费：取出后标记为已使用。"""
    from routers.topics import pop_next_topic
    import database
    c = database.conn()
    c.execute("INSERT INTO topic (account_id, content_type, content) VALUES (?,?,?)", (account_id, "干货", "弹出选题"))
    c.commit()
    c.close()
    row = pop_next_topic(account_id)
    assert row is not None
    assert row["content"] == "弹出选题"
    # 再取：已耗尽
    assert pop_next_topic(account_id) is None


def test_content_types_init(client, account_id):
    r = client.post(f"/api/topics/{account_id}/types/init")
    assert r.status_code == 200
    types = client.get(f"/api/topics/{account_id}/types").json()
    assert len(types) >= 3


def test_create_and_delete_content_type(client, account_id):
    r = client.post(f"/api/topics/{account_id}/types", json={"name": "测试类型", "prompt_template": "写一篇关于{topic}的文章"})
    assert r.status_code in (200, 201)
    tid = r.json()["id"]
    r2 = client.delete(f"/api/topics/{account_id}/types/{tid}")
    assert r2.status_code == 204
