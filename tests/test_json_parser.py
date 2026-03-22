"""json_parser の単体テスト + 消費者テスト（LLM出力サンプル）。"""

import json

import pytest

from bot_common.json_parser import extract_json_array, extract_json_object


# ---- 単体テスト ----


class TestExtractJsonArray:
    """extract_json_array の基本動作。"""

    def test_clean_json(self):
        text = '[{"a": 1}, {"a": 2}]'
        assert extract_json_array(text) == [{"a": 1}, {"a": 2}]

    def test_markdown_code_block(self):
        text = '```json\n[{"key": "value"}]\n```'
        assert extract_json_array(text) == [{"key": "value"}]

    def test_trailing_comma(self):
        text = '[{"a": 1}, {"a": 2},]'
        assert extract_json_array(text) == [{"a": 1}, {"a": 2}]

    def test_raw_newlines_in_string(self):
        text = '[{"text": "line1\nline2"}]'
        result = extract_json_array(text)
        assert result[0]["text"] == "line1\nline2"

    def test_surrounding_text(self):
        text = 'Here is the result:\n[{"id": 1}]\nDone!'
        assert extract_json_array(text) == [{"id": 1}]

    def test_empty_raises(self):
        with pytest.raises(json.JSONDecodeError):
            extract_json_array("no json here")

    def test_object_by_object_fallback(self):
        text = '{"a": 1}\n{"b": 2}'
        result = extract_json_array(text)
        assert len(result) == 2


class TestExtractJsonObject:
    """extract_json_object の基本動作。"""

    def test_clean_json(self):
        text = '{"key": "value"}'
        assert extract_json_object(text) == {"key": "value"}

    def test_markdown_code_block(self):
        text = '```json\n{"key": "value"}\n```'
        assert extract_json_object(text) == {"key": "value"}

    def test_surrounding_text(self):
        text = 'Result: {"score": 8.5} end'
        assert extract_json_object(text) == {"score": 8.5}

    def test_trailing_comma(self):
        text = '{"a": 1, "b": 2,}'
        assert extract_json_object(text) == {"a": 1, "b": 2}

    def test_empty_raises(self):
        with pytest.raises(json.JSONDecodeError):
            extract_json_object("no json")


# ---- 消費者テスト: LLM出力サンプル ----


class TestLLMOutputSamples:
    """実際のLLM出力パターンを再現するテスト。"""

    def test_claude_typical_response(self):
        """Claude API の典型的なレスポンス（前後テキスト付き）。"""
        text = """以下のJSON形式で結果を出力します：

```json
[
  {
    "title": "効率的な転職活動のコツ",
    "content": "転職活動では\\n1. 自己分析\\n2. 市場調査\\nが重要です。",
    "quality_score": 8.5
  }
]
```

以上が生成結果です。"""
        result = extract_json_array(text)
        assert len(result) == 1
        assert result[0]["quality_score"] == 8.5

    def test_claude_multi_object_no_array(self):
        """配列でなく個別オブジェクトが返されるケース。"""
        text = """{"title": "Post 1", "score": 7}
{"title": "Post 2", "score": 9}
{"title": "Post 3", "score": 6}"""
        result = extract_json_array(text)
        assert len(result) == 3
        assert result[1]["score"] == 9

    def test_nested_newlines_in_content(self):
        """日本語コンテンツ内の改行。"""
        text = """[{"text": "転職のポイント
1. 情報収集
2. スキル棚卸し
3. 面接準備"}]"""
        result = extract_json_array(text)
        assert "転職のポイント" in result[0]["text"]
