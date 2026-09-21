"""Read-only result display projection from an immutable execution definition.

Never read the current Configuration draft, convert legacy fields, or write a Job
or Result. Failure to resolve the display contract must not hide the raw result.
"""

from copy import deepcopy
from typing import Any, Awaitable, Callable, Dict, Optional

from services.extract_schema import check_schema, schema_hash

RevisionLoader = Callable[[str], Awaitable[Optional[Dict[str, Any]]]]


def _unavailable(reason: str) -> Dict[str, Any]:
    return {"status": "unavailable", "reason": reason}


def _display_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Do not expose extraction instructions through a member's result endpoint."""
    result = {key: deepcopy(value) for key, value in schema.items() if key != "description"}
    if "properties" in result:
        result["properties"] = {
            key: _display_schema(value) for key, value in result["properties"].items()
        }
    if isinstance(result.get("items"), dict):
        result["items"] = _display_schema(result["items"])
    return result


async def resolve_result_view(
    job: Optional[Dict[str, Any]],
    row: Dict[str, Any],
    load_revision: RevisionLoader,
) -> Dict[str, Any]:
    if not job or str(job.get("job_id")) != str(row.get("job_id")):
        return _unavailable("job_mismatch")
    if not job.get("tenant_id") or job["tenant_id"] != row.get("tenant_id"):
        return _unavailable("tenant_mismatch")

    spec = job.get("execution_spec")
    if isinstance(spec, dict) and spec:
        if spec.get("capability") != "extract" or spec.get("spec_version") != "1":
            return _unavailable("invalid_execution_spec")
        if row.get("config_revision_id") or job.get("configuration_revision_id"):
            return _unavailable("definition_mismatch")
        definition = spec.get("effective_params")
        origin = "execution_spec"
        ui: Dict[str, Any] = {}  # UI metadata is deliberately not added to Job snapshots.
    else:
        revision_id = job.get("configuration_revision_id")
        if not revision_id or str(revision_id) != str(row.get("config_revision_id")):
            return _unavailable("revision_mismatch")
        revision = await load_revision(str(revision_id))
        if not revision or str(revision.get("id")) != str(revision_id):
            return _unavailable("revision_unavailable")
        definition = revision.get("definition")
        origin = "revision"
        ui = definition.get("ui", {}) if isinstance(definition, dict) else {}

    if not isinstance(definition, dict):
        return _unavailable("definition_unavailable")
    schema = definition.get("data_schema")
    if check_schema(schema):
        return _unavailable("schema_unavailable")
    target = definition.get("target", "per_doc")
    if not isinstance(target, str) or target not in {"per_doc", "per_page"}:
        return _unavailable("target_invalid")
    digest = schema_hash(schema)
    engine = row.get("engine")
    if isinstance(engine, dict) and engine.get("schema_hash") not in (None, digest):
        return _unavailable("schema_hash_mismatch")
    return {
        "status": "available",
        "origin": origin,
        "target": target,
        "schema": _display_schema(schema),
        "schema_hash": digest,
        "ui": deepcopy(ui) if isinstance(ui, dict) else {},
    }
