# services/extract_schema.py
"""Extract schema 契约：JSON Schema 子集的白名单校验与取值校验（#32 v3.1）。

本轮子集：type / properties / items / required / enum / description /
format / additionalProperties。
- 根节点必须是 object（schema 描述单个实例，target 决定外层形状）；
- 不支持的关键字明确拒绝，不静默忽略、不改写 schema；
- format 仅支持 date，其余在提交时拒绝；
- 取值校验用 Draft 2020-12 + FormatChecker，错误带 JSON 路径。
"""

import hashlib
import json
from typing import Any, Dict, List

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

SUPPORTED_KEYWORDS = frozenset({
    "type",
    "properties",
    "items",
    "required",
    "enum",
    "description",
    "format",
    "additionalProperties",
})
SUPPORTED_TYPES = frozenset({
    "object",
    "array",
    "string",
    "number",
    "integer",
    "boolean",
    "null",
})
SUPPORTED_FORMATS = frozenset({"date"})
FORMAT_CHECKER = FormatChecker()


def check_schema(schema: Any) -> List[str]:
    """校验 schema 语法与子集白名单；返回错误列表（空列表表示可用）。"""
    if not isinstance(schema, dict):
        return ["data_schema 必须是 JSON 对象"]

    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        return [f"data_schema 语法非法: {exc.message}"]

    errors = _check_keywords(schema, "$")
    if schema.get("type") != "object":
        errors.append("$.type 必须是 object（schema 根节点只描述单个实例）")
    return errors


def validate_value(schema: Dict[str, Any], value: Any) -> List[Dict[str, str]]:
    """按 schema 校验一次抽取结果；返回 [{json_path, message}]（空表示通过）。"""
    validator = Draft202012Validator(schema, format_checker=FORMAT_CHECKER)
    issues: List[Dict[str, str]] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        path = "$" + "".join(
            f"[{part}]" if isinstance(part, int) else f".{part}"
            for part in error.absolute_path
        )
        issues.append({"json_path": path, "message": error.message})
    return issues


def schema_hash(schema: Dict[str, Any]) -> str:
    """稳定 hash（键序无关），用于 engine 元信息。"""
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_keywords(node: Any, path: str) -> List[str]:
    if not isinstance(node, dict):
        return [f"{path} 必须是 JSON 对象"]

    errors: List[str] = []
    for key in node:
        if key not in SUPPORTED_KEYWORDS:
            errors.append(f"{path}.{key} 不在本轮支持的关键字内")

    node_type = node.get("type")
    if node_type is not None:
        types = node_type if isinstance(node_type, list) else [node_type]
        if not types or any(str(item) not in SUPPORTED_TYPES for item in types):
            errors.append(f"{path}.type 非法: {node_type}")

    fmt = node.get("format")
    if fmt is not None and fmt not in SUPPORTED_FORMATS:
        errors.append(f"{path}.format 不支持: {fmt}（仅支持 {sorted(SUPPORTED_FORMATS)}）")

    required = node.get("required")
    if required is not None and (
        not isinstance(required, list) or any(not isinstance(item, str) for item in required)
    ):
        errors.append(f"{path}.required 必须是字符串数组")

    enum = node.get("enum")
    if enum is not None and (not isinstance(enum, list) or not enum):
        errors.append(f"{path}.enum 必须是非空数组")

    additional = node.get("additionalProperties")
    if additional is not None and not isinstance(additional, bool):
        errors.append(f"{path}.additionalProperties 仅支持布尔值")

    properties = node.get("properties")
    if properties is not None:
        if not isinstance(properties, dict):
            errors.append(f"{path}.properties 必须是对象")
        else:
            for name, subschema in properties.items():
                errors.extend(_check_keywords(subschema, f"{path}.properties.{name}"))

    items = node.get("items")
    if items is not None:
        if not isinstance(items, dict):
            errors.append(f"{path}.items 必须是 JSON 对象（不支持元组形式）")
        else:
            errors.extend(_check_keywords(items, f"{path}.items"))

    return errors
