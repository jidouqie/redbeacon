"""routers/account.py：账号 CRUD、MCP 状态查询。"""


def test_list_accounts_empty(client, tmp_db):
    r = client.get("/api/accounts")
    assert r.status_code == 200
    assert r.json() == []


def test_list_accounts_with_data(client, account_id):
    r = client.get("/api/accounts")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["id"] == account_id


def test_get_account(client, account_id):
    r = client.get(f"/api/accounts/{account_id}")
    assert r.status_code == 200
    assert r.json()["id"] == account_id


def test_get_account_not_found(client, account_id):
    r = client.get("/api/accounts/9999")
    assert r.status_code == 404


def test_mcp_status_not_running(client, account_id):
    r = client.get(f"/api/accounts/{account_id}/mcp/status")
    assert r.status_code == 200
    assert r.json()["running"] is False


def test_login_status_unknown_without_mcp(client, account_id):
    """未启动 MCP 时，登录状态查询应返回错误而非崩溃。"""
    r = client.get(f"/api/accounts/{account_id}/login/status")
    assert r.status_code in (200, 400, 503)
