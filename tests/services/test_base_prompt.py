# tests/services/test_base_prompt.py
"""抽取 Prompt 构建测试 — 字段描述进入 prompt，历史示例键不再注入。"""

from services.base import build_extraction_prompt
from services.configuration_service import build_extraction_config


def test_prompt_uses_field_hint_and_has_no_examples_section():
    config = {
        "name": "发票",
        "fields": [
            {
                "field_key": "invoice_date",
                "field_label": "开票日期",
                "field_type": "date",
                "extraction_hint": "输出 YYYY-MM-DD",
            }
        ],
    }

    prompt = build_extraction_prompt(config, "开票日期：2026年09月01日")

    assert "输出 YYYY-MM-DD" in prompt
    assert "参考示例" not in prompt
    assert "few-shot" not in prompt.lower()


def test_legacy_examples_key_is_ignored_when_building_prompt():
    configuration = {
        "id": "c-legacy",
        "name": "检测报告",
        "draft_definition": {
            "fields": [{"field_key": "sample_name", "field_label": "样品名称"}],
            "examples": [
                {
                    "example_input": "样品名称：小型断路器",
                    "example_output": {"sample_name": "小型断路器"},
                }
            ],
        },
    }

    config = build_extraction_config(configuration)
    prompt = build_extraction_prompt(config, "样品名称：小型断路器")

    assert "examples" not in config
    assert "小型断路器" not in prompt.split("现在，请处理用户提供的解析文本")[0]
    assert "参考示例" not in prompt
