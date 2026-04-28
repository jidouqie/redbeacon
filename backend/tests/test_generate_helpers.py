"""tasks/generate.py 纯函数：JSON 解析、嵌套引号修复、提示词填充。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tasks.generate import _fix_embedded_quotes, _parse_json_output


# ── _fix_embedded_quotes ──────────────────────────────────────────────────────

def test_fix_no_embedded_quotes():
    text = '{"title": "正常标题", "content": "正常内容"}'
    assert _fix_embedded_quotes(text) == text


def test_fix_embedded_quote_in_value():
    text = '{"title": "总说"随时辞职"的同事", "content": "正文"}'
    fixed = _fix_embedded_quotes(text)
    import json
    data = json.loads(fixed)
    assert "随时辞职" in data["title"]


def test_fix_already_escaped():
    text = r'{"title": "含 \"转义\" 引号"}'
    fixed = _fix_embedded_quotes(text)
    import json
    data = json.loads(fixed)
    assert "转义" in data["title"]


def test_fix_nested_multiple_quotes():
    text = '{"x": "a "b" c "d" e"}'
    fixed = _fix_embedded_quotes(text)
    import json
    data = json.loads(fixed)
    assert data["x"]  # 能解析即可


# ── _parse_json_output ────────────────────────────────────────────────────────

def test_parse_clean_json():
    raw = '{"title": "好标题", "content": "好内容", "tags": ["干货"]}'
    result = _parse_json_output(raw)
    assert result["title"] == "好标题"
    assert result["tags"] == ["干货"]


def test_parse_json_in_code_block():
    raw = '```json\n{"title": "标题", "content": "内容", "tags": []}\n```'
    result = _parse_json_output(raw)
    assert result["title"] == "标题"


def test_parse_json_with_surrounding_text():
    raw = '这是AI回复：\n{"title": "T", "content": "C", "tags": []} 希望有帮助'
    result = _parse_json_output(raw)
    assert result["title"] == "T"


def test_parse_json_with_embedded_quotes():
    raw = '{"title": "总说"随时辞职"的同事", "content": "内容", "tags": []}'
    result = _parse_json_output(raw)
    assert result["title"] != ""
    assert result["content"] == "内容"


def test_parse_fallback_no_json():
    """无法解析时退回到逐行提取，至少返回有效结构。"""
    raw = "标题：这是标题\n这是第一段正文\n这是第二段正文"
    result = _parse_json_output(raw)
    assert isinstance(result, dict)
    assert "title" in result
    assert "content" in result
    assert "tags" in result


def test_parse_returns_dict_always():
    result = _parse_json_output("完全无法解析的随机字符串 @#$%")
    assert isinstance(result, dict)
