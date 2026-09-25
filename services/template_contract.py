"""Adapter for the canonical OCR extraction template."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "template/OCR训练-基本信息-药物注册类/1-空JSON-药物注册类.json"


def load_template(path: str | Path = TEMPLATE_PATH) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as fh:
        template = json.load(fh)
    if not isinstance(template, dict) or not isinstance(template.get("fields"), list):
        raise ValueError("模板必须包含 fields 数组")
    return template


def _field_schema(field: Mapping[str, Any]) -> dict[str, Any]:
    typ = field.get("type")
    if typ == "enum":
        return {"type": "string", "enum": list(field.get("options") or [])}
    if typ == "date":
        return {"type": "string", "format": "date"}
    if typ == "number":
        return {"type": "number"}
    if typ == "product[]":
        props: dict[str, Any] = {}
        required: list[str] = []
        for item in field.get("itemFields") or []:
            item_schema = _field_schema(item)
            props[str(item["key"])] = item_schema
            if item.get("required"):
                required.append(str(item["key"]))
        result: dict[str, Any] = {"type": "array", "items": {"type": "object", "properties": props, "additionalProperties": False}}
        if required:
            result["items"]["required"] = required
        return result
    return {"type": "string"}


def template_to_schema(template: Mapping[str, Any] | None = None) -> dict[str, Any]:
    template = template or load_template()
    properties = {str(f["key"]): _field_schema(f) for f in template["fields"]}
    return {"type": "object", "properties": properties, "additionalProperties": False}


def template_field_keys(template: Mapping[str, Any] | None = None) -> list[str]:
    return [str(f["key"]) for f in (template or load_template())["fields"]]


def project_fields(values: Mapping[str, Any] | None, *, template: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Project flat values into the canonical template, retaining all declarations."""
    template = template or load_template()
    values = values or {}
    fields: list[dict[str, Any]] = []
    for declaration in template["fields"]:
        key = str(declaration["key"])
        item = dict(declaration)
        value = values.get(key, "")
        if value is None:
            value = ""
        item["value"] = value
        if value != "":
            if isinstance(values.get(f"{key}__meta"), Mapping):
                item.update(values[f"{key}__meta"])
        fields.append(item)
    result = {k: template[k] for k in ("scene", "trialType", "registrationType") if k in template}
    result["fields"] = fields
    return result


def template_consistency(template: Mapping[str, Any] | None = None) -> list[str]:
    template = template or load_template()
    errors: list[str] = []
    fields = template.get("fields")
    if not isinstance(fields, list) or len(fields) != 40:
        errors.append(f"模板字段数必须为 40，实际 {len(fields) if isinstance(fields, list) else 'invalid'}")
    seen: set[str] = set()
    for field in fields or []:
        key = field.get("key")
        if not key or key in seen:
            errors.append(f"字段 key 缺失或重复: {key}")
        seen.add(key)
        if field.get("type") == "enum" and not field.get("options"):
            errors.append(f"枚举字段缺少 options: {key}")
        if field.get("type") == "product[]" and not field.get("itemFields"):
            errors.append(f"产品数组缺少 itemFields: {key}")
    return errors


def is_canonical_schema(schema: Mapping[str, Any], *, template: Mapping[str, Any] | None = None) -> bool:
    """Return whether a runtime schema has the canonical 40-field shape.

    Descriptions may differ between a Configuration revision and the source
    template; field keys and value-shape keywords are the compatibility guard.
    """
    expected = template_to_schema(template)
    actual = schema if isinstance(schema, Mapping) else {}

    def shape(node: Any) -> Any:
        if not isinstance(node, Mapping):
            return node
        result: dict[str, Any] = {}
        for key in ("type", "enum", "format", "required", "properties", "items"):
            if key not in node:
                continue
            value = node[key]
            if key == "properties" and isinstance(value, Mapping):
                value = {str(name): shape(child) for name, child in value.items()}
            elif key == "items":
                value = shape(value)
            result[key] = value
        return result

    return shape(actual) == shape(expected)
