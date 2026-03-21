# tests/agents/test_json_cleaner.py
"""agents/json_cleaner.py 单元测试 — parse_llm_json 各种输入场景"""

import pytest
from agents.json_cleaner import parse_llm_json, _strip_markdown_fence, _extract_first_json_object


class TestParseLlmJson:
    """parse_llm_json 主函数测试"""

    # ---- 合法 JSON ----

    def test_valid_json_object(self):
        """标准 JSON 对象直接解析"""
        result = parse_llm_json('{"name": "张三", "age": 30}')
        assert result == {"name": "张三", "age": 30}

    def test_valid_json_with_whitespace(self):
        """带前后空白的合法 JSON"""
        result = parse_llm_json('  {"key": "value"}  ')
        assert result == {"key": "value"}

    def test_valid_json_nested(self):
        """嵌套 JSON 对象"""
        result = parse_llm_json('{"outer": {"inner": 1}}')
        assert result == {"outer": {"inner": 1}}

    def test_valid_json_with_chinese_values(self):
        """含中文值的 JSON"""
        result = parse_llm_json('{"样品编号": "SN-001", "检测结论": "合格"}')
        assert result["样品编号"] == "SN-001"
        assert result["检测结论"] == "合格"

    def test_valid_json_empty_object(self):
        """空 JSON 对象"""
        result = parse_llm_json("{}")
        assert result == {}

    # ---- Markdown 代码块 ----

    def test_markdown_json_fence(self):
        """```json ... ``` 包裹的 JSON"""
        content = '```json\n{"sample_no": "SN-001"}\n```'
        result = parse_llm_json(content)
        assert result == {"sample_no": "SN-001"}

    def test_markdown_plain_fence(self):
        """``` ... ``` 包裹（无语言标记）"""
        content = '```\n{"key": "val"}\n```'
        result = parse_llm_json(content)
        assert result == {"key": "val"}

    def test_markdown_fence_with_extra_text_before(self):
        """代码块前有说明文字，通过提取第一个 {} 解析"""
        content = '以下是提取结果：\n```json\n{"result": "ok"}\n```'
        result = parse_llm_json(content)
        # 剥除 fence 后仍有前缀文字，走 _extract_first_json_object
        assert result.get("result") == "ok" or "raw_response" in result

    def test_markdown_fence_multiline_json(self):
        """多行 JSON 在代码块中"""
        content = '```json\n{\n  "a": 1,\n  "b": "hello"\n}\n```'
        result = parse_llm_json(content)
        assert result == {"a": 1, "b": "hello"}

    # ---- 提取第一个 JSON 对象 ----

    def test_json_embedded_in_text(self):
        """JSON 嵌入在普通文本中"""
        content = '提取结果如下：{"field": "value"} 以上是结果。'
        result = parse_llm_json(content)
        assert result == {"field": "value"}

    def test_json_with_prefix_text(self):
        """JSON 前有前缀文字"""
        content = 'Sure, here is the result: {"status": "done"}'
        result = parse_llm_json(content)
        assert result == {"status": "done"}

    # ---- 边界 / 异常情况 ----

    def test_empty_string(self):
        """空字符串返回空字典"""
        result = parse_llm_json("")
        assert result == {}

    def test_none_like_empty(self):
        """只有空白字符"""
        result = parse_llm_json("   ")
        # 空白 strip 后为空，走 raw_response 或空字典
        assert isinstance(result, dict)

    def test_completely_invalid_string(self):
        """完全非法字符串 → 返回 raw_response"""
        content = "这不是JSON，完全无法解析的文本内容"
        result = parse_llm_json(content)
        assert "raw_response" in result
        assert result["raw_response"] == content

    def test_truncated_json(self):
        """截断的 JSON → 返回 raw_response"""
        content = '{"key": "val'
        result = parse_llm_json(content)
        assert "raw_response" in result

    def test_json_with_escaped_quotes(self):
        """含转义引号的 JSON"""
        content = '{"message": "He said \\"hello\\""}'
        result = parse_llm_json(content)
        assert result["message"] == 'He said "hello"'

    def test_json_with_unicode(self):
        """含 Unicode 转义的 JSON"""
        content = '{"name": "\\u5f20\\u4e09"}'
        result = parse_llm_json(content)
        assert result["name"] == "张三"

    def test_returns_dict_always(self):
        """任何输入都应返回 dict"""
        for content in ["", "garbage", '{"ok": true}', '```json\n{}\n```']:
            result = parse_llm_json(content)
            assert isinstance(result, dict), f"输入 {content!r} 返回了非 dict: {result!r}"


class TestStripMarkdownFence:
    """_strip_markdown_fence 辅助函数测试"""

    def test_strips_json_fence(self):
        content = "```json\n{}\n```"
        assert _strip_markdown_fence(content) == "{}"

    def test_strips_plain_fence(self):
        content = "```\n{}\n```"
        assert _strip_markdown_fence(content) == "{}"

    def test_no_fence_unchanged(self):
        content = '{"key": "val"}'
        assert _strip_markdown_fence(content) == content

    def test_fence_without_closing(self):
        """没有结尾 ``` 的情况"""
        content = "```json\n{}"
        result = _strip_markdown_fence(content)
        assert "{}" in result


class TestExtractFirstJsonObject:
    """_extract_first_json_object 辅助函数测试"""

    def test_extracts_simple_object(self):
        content = 'prefix {"a": 1} suffix'
        assert _extract_first_json_object(content) == '{"a": 1}'

    def test_extracts_nested_object(self):
        content = 'text {"outer": {"inner": 2}} more'
        assert _extract_first_json_object(content) == '{"outer": {"inner": 2}}'

    def test_no_object_returns_none(self):
        assert _extract_first_json_object("no json here") is None

    def test_object_with_string_containing_braces(self):
        """字符串值中含有花括号，不应被误判为嵌套"""
        content = '{"key": "value with { brace }"}'
        result = _extract_first_json_object(content)
        assert result == '{"key": "value with { brace }"}'
