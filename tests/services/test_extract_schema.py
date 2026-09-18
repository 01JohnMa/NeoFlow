# tests/services/test_extract_schema.py
"""Extract schema 契约测试：白名单、nullable/enum 语义、format 与取值校验。"""

from services.extract_schema import check_schema, schema_hash, validate_value


def _schema(**overrides):
    base = {
        "type": "object",
        "properties": {
            "report_no": {"type": "string", "description": "报告编号"},
            "conclusion": {"type": ["string", "null"], "enum": ["合格", "不合格", None]},
            "line_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"amount": {"type": "number"}},
                    "required": ["amount"],
                },
            },
        },
        "required": ["report_no"],
        "additionalProperties": False,
    }
    base.update(overrides)
    return base


class TestCheckSchema:
    def test_valid_schema_passes(self):
        assert check_schema(_schema()) == []

    def test_root_must_be_object(self):
        errors = check_schema({"type": "array", "items": {"type": "string"}})
        assert any("object" in item for item in errors)

    def test_unsupported_keyword_rejected(self):
        errors = check_schema(_schema(anyOf=[{"type": "string"}]))
        assert any("anyOf" in item for item in errors)

    def test_business_field_named_like_keyword_allowed(self):
        schema = _schema(
            properties={
                "format": {"type": "string"},
                "items": {"type": "string"},
                "required": {"type": "string"},
            }
        )
        assert check_schema(schema) == []

    def test_unknown_format_rejected_and_date_accepted(self):
        bad = _schema(properties={"d": {"type": "string", "format": "email"}})
        assert any("format" in item for item in check_schema(bad))
        good = _schema(properties={"d": {"type": "string", "format": "date"}})
        assert check_schema(good) == []

    def test_additional_properties_must_be_bool(self):
        bad = _schema(additionalProperties={"type": "string"})
        assert any("additionalProperties" in item for item in check_schema(bad))

    def test_empty_enum_rejected(self):
        bad = _schema(properties={"c": {"type": "string", "enum": []}})
        assert any("enum" in item for item in check_schema(bad))

    def test_nested_keyword_error_reports_path(self):
        bad = _schema(
            properties={
                "buyer": {
                    "type": "object",
                    "properties": {"name": {"type": "string", "minLength": 1}},
                }
            }
        )
        errors = check_schema(bad)
        assert any("$.properties.buyer.properties.name" in item for item in errors)


class TestValidateValue:
    def test_valid_value_passes(self):
        value = {
            "report_no": "WT-1",
            "conclusion": None,
            "line_items": [{"amount": 1.5}],
        }
        assert validate_value(_schema(), value) == []

    def test_missing_required_reports_root(self):
        issues = validate_value(_schema(), {"conclusion": "合格"})
        assert issues and issues[0]["json_path"] == "$"

    def test_array_item_error_reports_index(self):
        value = {"report_no": "WT-1", "line_items": [{"amount": 1}, {"amount": "x"}]}
        issues = validate_value(_schema(), value)
        assert any(item["json_path"] == "$.line_items[1].amount" for item in issues)

    def test_enum_violation_reports_path(self):
        value = {"report_no": "WT-1", "conclusion": "待定"}
        issues = validate_value(_schema(), value)
        assert any(item["json_path"] == "$.conclusion" for item in issues)

    def test_nullable_type_alone_does_not_allow_null_when_enum_lacks_null(self):
        schema = _schema(
            properties={
                "report_no": {"type": "string"},
                "conclusion": {"type": ["string", "null"], "enum": ["A", "B"]},
            }
        )
        issues = validate_value(schema, {"report_no": "WT-1", "conclusion": None})
        assert any(item["json_path"] == "$.conclusion" for item in issues)

    def test_null_in_enum_allows_null(self):
        schema = _schema(
            properties={
                "report_no": {"type": "string"},
                "conclusion": {"type": ["string", "null"], "enum": ["A", None]},
            }
        )
        assert validate_value(schema, {"report_no": "WT-1", "conclusion": None}) == []

    def test_date_format_is_enforced(self):
        schema = _schema(
            properties={
                "report_no": {"type": "string"},
                "sampling_date": {"type": "string", "format": "date"},
            }
        )
        assert validate_value(schema, {"report_no": "WT-1", "sampling_date": "2025-08-14"}) == []
        issues = validate_value(schema, {"report_no": "WT-1", "sampling_date": "2025-13-01"})
        assert issues and issues[0]["json_path"] == "$.sampling_date"

    def test_additional_property_rejected(self):
        issues = validate_value(_schema(), {"report_no": "WT-1", "extra": 1})
        assert issues


class TestSchemaHash:
    def test_hash_is_key_order_insensitive(self):
        first = {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}}}
        second = {"properties": {"a": {"type": "string"}}, "required": ["a"], "type": "object"}
        assert schema_hash(first) == schema_hash(second)
