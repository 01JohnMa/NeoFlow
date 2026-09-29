# services/schema_queries.py
"""Schema→retrieval-query mapping: the single source of truth shared by the
deterministic source-page router and the Agentic initial search.

Both retrieval paths must start from identical query semantics so their
quality measurements stay comparable (ADR-0011).
"""

from typing import Any, Dict, Mapping


def _escape_pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _leaf_queries(schema: Mapping[str, Any], path: str = "") -> Dict[str, str]:
    properties = schema.get("properties") if isinstance(schema, Mapping) else None
    if not isinstance(properties, Mapping):
        if not path:
            return {}
        enum = schema.get("enum")
        enum_text = " ".join(str(item) for item in enum) if isinstance(enum, list) else ""
        query = " ".join(
            str(value)
            for value in (path, schema.get("description", ""), enum_text)
            if value
        ).strip()
        return {path: query} if query else {}
    queries: Dict[str, str] = {}
    for key, node in properties.items():
        if not isinstance(node, Mapping):
            continue
        escaped = _escape_pointer_token(str(key))
        child = f"{path}/{escaped}" if path else escaped
        queries.update(_leaf_queries(node, child))
    return queries


def schema_field_queries(schema: Mapping[str, Any]) -> Dict[str, str]:
    """Map each schema leaf path to its query: "path + description + enum text"."""
    if not isinstance(schema, Mapping):
        return {}
    return _leaf_queries(schema)
