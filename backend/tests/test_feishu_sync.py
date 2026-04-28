"""tasks/feishu_sync.py：_str() 辅助函数 + run_feishu_sync 无配置时的行为。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tasks.feishu_sync import _str, run_feishu_sync


# ── _str ──────────────────────────────────────────────────────────────────────

def test_str_none():
    assert _str(None) == ""


def test_str_plain_string():
    assert _str("  hello  ") == "hello"


def test_str_rich_text_list():
    val = [{"type": "text", "text": "段落一"}, {"type": "text", "text": "段落二"}]
    assert _str(val) == "段落一段落二"


def test_str_rich_text_with_non_dict():
    val = [{"type": "text", "text": "有效"}, "忽略字符串"]
    assert _str(val) == "有效"


def test_str_number():
    assert _str(42) == "42"


def test_str_empty_list():
    assert _str([]) == ""


# ── run_feishu_sync 无配置时静默返回 0 ────────────────────────────────────────

def test_sync_returns_zero_without_config(tmp_db):
    count = run_feishu_sync(account_id=1)
    assert count == 0


def test_sync_returns_zero_partial_config(tmp_db):
    import config
    config.set("feishu_app_id", "cli_test")
    # 缺少 app_secret / app_token / table_id → 仍应返回 0
    count = run_feishu_sync(account_id=1)
    assert count == 0
