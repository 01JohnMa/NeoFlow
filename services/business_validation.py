"""Generic validation for template-projected extraction results."""
from __future__ import annotations

import re
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker

_NUMBER = re.compile(r"^\s*[-+]?\d+(?:\.\d+)?\s*$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LIST_MARK = re.compile(r"(?:^|[\n；;])\s*(?:\d+[.)、]|[①②③④⑤⑥⑦⑧⑨⑩])")


def _empty(value: Any) -> bool:
    return value is None or value == ""


def _issues_for_field(field: Mapping[str, Any], value: Any, *, page_numbers: set[int] | None) -> list[dict[str, Any]]:
    key, typ = str(field.get("key")), field.get("type")
    if _empty(value):
        return []
    issues: list[dict[str, Any]] = []
    if typ == "enum" and value not in (field.get("options") or []):
        issues.append({"key": key, "code": "invalid_enum", "message": "值不在 options 中"})
    if typ == "date" and (not isinstance(value, str) or not _DATE.fullmatch(value)):
        issues.append({"key": key, "code": "invalid_date", "message": "日期必须为 yyyy-MM-dd"})
    if typ == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
        issues.append({"key": key, "code": "invalid_number", "message": "必须为数字"})
    if typ == "string" and isinstance(value, str) and field.get("hint", "").find("逐条") >= 0:
        if _LIST_MARK.search(value):
            nums = [int(x) for x in re.findall(r"(?:^|[\n；;])\s*(\d+)[.)、]", value)]
            if nums and nums != list(range(nums[0], nums[0] + len(nums))):
                issues.append({"key": key, "code": "incomplete_list", "message": "编号列表可能跳项"})
    if typ == "product[]":
        if not isinstance(value, list):
            issues.append({"key": key, "code": "invalid_product_array", "message": "必须为数组"})
        else:
            for i, product in enumerate(value):
                if not isinstance(product, Mapping) or not str(product.get("name") or "").strip():
                    issues.append({"key": key, "code": "empty_product_name", "index": i, "message": "产品名不能为空"})
                for item in field.get("itemFields") or []:
                    item_value = product.get(item.get("key")) if isinstance(product, Mapping) else None
                    if not _empty(item_value) and item.get("type") == "enum" and item_value not in (item.get("options") or []):
                        issues.append({"key": key, "code": "invalid_product_enum", "index": i, "field": item.get("key"), "message": "子字段不在 options 中"})
    return issues


def validate_template_values(template: Mapping[str, Any], values: Mapping[str, Any], *, page_numbers: set[int] | None = None, evidence: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return diagnostics; empty values are unresolved and intentionally valid."""
    issues: list[dict[str, Any]] = []
    for field in template.get("fields") or []:
        key = str(field.get("key"))
        issues.extend(_issues_for_field(field, values.get(key, ""), page_numbers=page_numbers))
    schema = _schema_from_template(template)
    material = {k: v for k, v in values.items() if not _empty(v) and not k.endswith("__meta")}
    for error in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(material):
        issues.append({"key": ".".join(str(x) for x in error.absolute_path), "code": "schema", "message": error.message})
    if evidence:
        for key, refs in evidence.items():
            for ref in refs if isinstance(refs, list) else []:
                page = ref.get("page") if isinstance(ref, Mapping) else None
                if page_numbers is not None and page is not None and page not in page_numbers:
                    issues.append({"key": key, "code": "evidence_page_out_of_range", "message": f"证据页 {page} 不在本次输入范围"})
    return issues


def _schema_from_template(template: Mapping[str, Any]) -> dict[str, Any]:
    from services.template_contract import template_to_schema
    return template_to_schema(template)
