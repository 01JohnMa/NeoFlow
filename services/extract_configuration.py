"""Extract authoring contract. No legacy-fields conversion and no execution IO.

The JSON Schema is authoritative; UI metadata contains only labels and order.
New configurations may start with an explicitly created empty object schema.
"""

from copy import deepcopy
from typing import Any, Dict, Iterator, Tuple

from services.extract_schema import check_schema


class ExtractConfigurationError(ValueError):
    """An invalid authoring definition; report to the caller instead of normalizing it away."""


EXTRACTION_STRATEGIES = ("full_document", "source_page_routed", "agentic_source_page_routed")


def escape_pointer_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def field_nodes(schema: Dict[str, Any], path: str = "") -> Iterator[Tuple[str, Dict[str, Any]]]:
    for key, node in schema.get("properties", {}).items():
        child_path = f"{path}/properties/{escape_pointer_token(key)}"
        yield child_path, node
        yield from field_nodes(node, child_path)
    if isinstance(schema.get("items"), dict):
        yield from field_nodes(schema["items"], f"{path}/items")


def empty_extract_definition() -> Dict[str, Any]:
    """An intentional new draft, not a fallback for missing/invalid saved schemas."""
    return {
        "target": "per_doc",
        "data_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "ui": {},
        "extraction_strategy": "full_document",
    }


def validate_extract_definition(definition: Any) -> Dict[str, Any]:
    """Validate and copy a complete definition; never convert old fields or fill results.

    The execution schema is neither rewritten nor narrowed to the Builder profile.
    Unknown configuration keys are rejected so an ignored setting cannot appear saved.
    """
    if not isinstance(definition, dict):
        raise ExtractConfigurationError("Extract definition 必须是 JSON 对象")
    unknown = set(definition) - {"target", "data_schema", "ui", "extraction_strategy"}
    if unknown:
        raise ExtractConfigurationError(
            "Extract 只接受 target/data_schema/ui/extraction_strategy，不支持这些配置键："
            + ", ".join(sorted(unknown))
        )
    if "data_schema" not in definition:
        raise ExtractConfigurationError("缺少 data_schema；不再支持 fields 或历史格式转换")
    issues = check_schema(definition["data_schema"])
    if issues:
        raise ExtractConfigurationError("; ".join(issues))
    target = definition.get("target", "per_doc")
    if not isinstance(target, str) or target not in {"per_doc", "per_page"}:
        raise ExtractConfigurationError("target 只支持 per_doc/per_page")

    if "extraction_strategy" in definition:
        strategy = definition["extraction_strategy"]
        if not isinstance(strategy, str) or strategy not in EXTRACTION_STRATEGIES:
            raise ExtractConfigurationError(
                "extraction_strategy 当前只支持 full_document/source_page_routed/agentic_source_page_routed；旧 page_routed 已下线"
            )
        if strategy in {"source_page_routed", "agentic_source_page_routed"} and target != "per_doc":
            raise ExtractConfigurationError(
                "source_page_routed/agentic_source_page_routed 当前只支持 per_doc"
            )

    schema = definition["data_schema"]
    ui = definition.get("ui", {})
    if not isinstance(ui, dict):
        raise ExtractConfigurationError("ui 必须是按 schema JSON Pointer 索引的对象")
    valid_paths = {path for path, _ in field_nodes(schema)}
    for path, metadata in ui.items():
        if path not in valid_paths:
            raise ExtractConfigurationError(f"ui 路径不存在或不是字段节点：{path}")
        if not isinstance(metadata, dict) or set(metadata) - {"label", "order"}:
            raise ExtractConfigurationError(f"ui[{path}] 只允许 label/order")
        if "label" in metadata and not isinstance(metadata["label"], str):
            raise ExtractConfigurationError(f"ui[{path}].label 必须是字符串")
        if "order" in metadata and (
            type(metadata["order"]) is not int or metadata["order"] < 0
        ):
            raise ExtractConfigurationError(f"ui[{path}].order 必须是非负整数")

    # Keep absence/presence and schema content intact; do not add required/null/defaults.
    return deepcopy(definition)


def merge_extract_definition(base: Any, patch: Any) -> Dict[str, Any]:
    """Atomic replacement of schema/ui, not a recursive merge of schema properties."""
    if not isinstance(base, dict) or not isinstance(patch, dict):
        raise ExtractConfigurationError("Extract definition 与补丁必须是 JSON 对象")
    return validate_extract_definition({**base, **patch})


def draft_fields_definition(fields: Any, description: str = "") -> Dict[str, Any]:
    """Compile a *new AI proposal* at the authoring boundary, never saved legacy data.

    The existing confirmation UI remains a simple three-type proposal editor. Its
    transient rows are not stored or used at execution time; enum/object lists are
    added with the schema Builder after creation. This is not a migration adapter.
    """
    if not isinstance(fields, list) or not fields:
        raise ExtractConfigurationError("至少需要一个确认字段")
    mapping = {
        "text": {"type": "string"},
        "date": {"type": "string", "format": "date"},
        "number": {"type": "number"},
    }
    definition = empty_extract_definition()
    schema = definition["data_schema"]
    schema["description"] = description
    for index, field in enumerate(fields):
        if not isinstance(field, dict):
            raise ExtractConfigurationError("AI 草拟字段必须是对象")
        key = field.get("field_key")
        if not isinstance(key, str) or not key.strip() or key != key.strip():
            raise ExtractConfigurationError("字段键名不能为空或包含首尾空白")
        if key in schema["properties"]:
            raise ExtractConfigurationError(f"同级字段键名重复：{key}")
        kind = field.get("field_type")
        if kind not in mapping:
            raise ExtractConfigurationError(f"AI 草拟字段类型不支持：{kind}")
        label = field.get("field_label", key)
        hint = field.get("extraction_hint", "")
        if not isinstance(label, str) or not isinstance(hint, str):
            raise ExtractConfigurationError(f"{key} 的标签/抽取说明必须是字符串")
        node = {**mapping[kind], "description": hint.strip() or label or key}
        if kind == "date":
            node["description"] += "；仅在原文有完整年月日时输出 YYYY-MM-DD，不补月初或月末。"
        schema["properties"][key] = node
        definition["ui"][f"/properties/{escape_pointer_token(key)}"] = {
            "label": label,
            "order": index,
        }
    return validate_extract_definition(definition)
