# tests/services/test_extract_prompt.py
"""Extract prompt 测试：消息构造、修复消息、严格 JSON 解析与预算估算。"""

import pytest

from services.extract_prompt import (
    StrictJSONError,
    build_extract_messages,
    build_repair_messages,
    estimate_tokens,
    fits_context,
    strict_json_loads,
)

SCHEMA = {
    "type": "object",
    "properties": {"report_no": {"type": "string", "description": "报告编号"}},
    "required": ["report_no"],
    "additionalProperties": False,
}


class TestBuildMessages:
    def test_includes_rules_schema_target_and_source(self):
        messages = build_extract_messages(
            schema=SCHEMA,
            target="per_doc",
            source_text="<page no=\"1\">报告编号：WT-1</page>",
        )
        assert messages[0]["role"] == "system"
        assert "只依据" in messages[0]["content"]
        user = messages[1]["content"]
        assert '"report_no"' in user
        assert "per_doc" not in user  # 说明文字而不是 target 字面量
        assert "直接输出该 JSON 对象" in user
        assert "报告编号：WT-1" in user

    def test_target_guidance_varies(self):
        page = build_extract_messages(schema=SCHEMA, target="per_page", source_text="x")
        assert "仅从该页" in page[1]["content"]

    def test_invalid_target_rejected(self):
        with pytest.raises(ValueError):
            build_extract_messages(schema=SCHEMA, target="per_chunk", source_text="x")


class TestRepairMessages:
    def test_appends_previous_output_and_error_paths(self):
        original = build_extract_messages(schema=SCHEMA, target="per_doc", source_text="x")
        repaired = build_repair_messages(
            original,
            previous_output='{"conclusion": "合格"}',
            errors=[{"json_path": "$.report_no", "message": "'report_no' is a required property"}],
        )
        assert repaired[: len(original)] == original
        assert repaired[-2] == {"role": "assistant", "content": '{"conclusion": "合格"}'}
        assert "路径 $.report_no" in repaired[-1]["content"]
        assert "required" in repaired[-1]["content"]

    def test_error_list_is_capped(self):
        original = build_extract_messages(schema=SCHEMA, target="per_doc", source_text="x")
        errors = [{"json_path": f"$.f{i}", "message": "bad"} for i in range(30)]
        repaired = build_repair_messages(original, previous_output="{}", errors=errors)
        assert repaired[-1]["content"].count("- 路径") == 10


class TestStrictJsonLoads:
    def test_plain_and_fenced_json(self):
        assert strict_json_loads('{"a": 1}') == {"a": 1}
        assert strict_json_loads('```json\n{"a": 1}\n```') == {"a": 1}
        assert strict_json_loads('```\n{"a": 1}\n```') == {"a": 1}

    def test_rejects_duplicate_keys(self):
        with pytest.raises(StrictJSONError):
            strict_json_loads('{"a": 1, "a": 2}')

    def test_rejects_nan_and_infinity(self):
        for content in (
            '{"a": NaN}',
            '{"a": Infinity}',
            '{"a": -Infinity}',
            '{"a": 1e400}',
        ):
            with pytest.raises(StrictJSONError):
                strict_json_loads(content)

    def test_rejects_trailing_content(self):
        with pytest.raises(StrictJSONError):
            strict_json_loads('{"a": 1} tail')

    def test_rejects_empty_and_non_json(self):
        for content in ("", "   ", "not json"):
            with pytest.raises(StrictJSONError):
                strict_json_loads(content)


class TestBudget:
    def test_estimate_grows_with_text_and_penalizes_cjk(self):
        assert estimate_tokens("") == 0
        assert estimate_tokens("中文内容") > estimate_tokens("abcdef")
        assert estimate_tokens("abc") >= estimate_tokens("ab")

    def test_fits_context(self):
        assert fits_context("短文本", context_window=1000, max_output_tokens=100)
        long_text = "中" * 2000
        assert not fits_context(long_text, context_window=1000, max_output_tokens=100)
