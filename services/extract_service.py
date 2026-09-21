# services/extract_service.py
"""Extract handler：绑定 ParseResult → 单元执行 → 组装 → 认领感知原子交卷。

本轮（#32 v3.1 / ADR-0009）：
- target：per_doc（整文单实例）、per_page（逐页单实例，结果按页序数组）；
  per_table_row 明确拒绝；
- 整文直抽：超上下文明确失败，不截断、不做分块；
- 严格校验（JSON Schema 子集）失败最多修复一次；请求预算由单元执行器计数；
- 绑定写一次（写进 Job 的 parse_result_id），重试只读绑定；
- 心跳覆盖绑定→交卷确认，失锁即停；成功交卷响应丢失时回读/重试，绝不盲目标失败；
- 所有失败路径走认领感知交卷。
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Awaitable, Dict, List, Optional, Tuple

import httpx
from loguru import logger
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

from api.jobs import (
    bind_extract_parse_result,
    commit_extract_job,
    consume_extract_request,
    ensure_extract_budget,
    get_job,
    renew_job_claim,
)
from config.settings import settings
from services.extract_prompt import (
    StrictJSONError,
    build_extract_messages,
    build_repair_messages,
    build_routed_messages,
    fits_context,
    strict_json_loads,
)
from services.extract_schema import check_schema, schema_hash, validate_value
from services.llm_invoke import LLMResult, invoke_llm
from services.page_index import (
    EmbeddingProfile,
    PageCandidate,
    PageIndexError,
    PageIndexService,
)
from services.parse_service import ensure_parse_result
from services.result_service import result_service
from services.supabase_service import supabase_service

EXTRACT_CAPABILITY = "extract"
SPEC_VERSION = "1"
SUPPORTED_TARGETS = ("per_doc", "per_page")
FULL_DOCUMENT_STRATEGY = "full_document"
PAGE_ROUTED_STRATEGY = "page_routed"
SUPPORTED_STRATEGIES = (FULL_DOCUMENT_STRATEGY, PAGE_ROUTED_STRATEGY)
MAX_REQUESTS_PER_UNIT = 3
ENGINE_MAX_BYTES = 16384
ENGINE_MAX_CALLS = 20
EXTRACT_SAMPLE_KEY = "extract"
page_index_service = PageIndexService()

class ExtractFailure(Exception):
    """可解释的执行失败（reason 进 Job error，不发正式结果）。"""

    def __init__(self, reason: str, message: str = ""):
        super().__init__(f"{reason}: {message}" if message else reason)
        self.reason = reason
        self.message = message


def build_execution_spec(definition: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """构造执行快照：原样保留 target/data_schema 的存在性与取值。

    显式提供的非法值（如 data_schema=[]、target=""）必须被下游校验拒绝，
    不能被快照层悄悄替换成默认值。
    """
    definition = definition if isinstance(definition, dict) else {}
    effective_params = {
        key: definition[key]
        for key in ("target", "data_schema", "extraction_strategy")
        if key in definition
    }
    return {
        "capability": EXTRACT_CAPABILITY,
        "spec_version": SPEC_VERSION,
        "effective_params": effective_params,
    }


def resolve_extract_spec(
    job: Dict[str, Any],
    revision: Optional[Dict[str, Any]] = None,
    configuration: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """解析执行定义：草稿快照（execution_spec）或已发布 Revision。"""
    spec = job.get("execution_spec")
    if isinstance(spec, dict) and spec:
        if spec.get("capability") != EXTRACT_CAPABILITY:
            raise ExtractFailure("unsupported_capability", str(spec.get("capability")))
        if spec.get("spec_version") != SPEC_VERSION:
            raise ExtractFailure("unsupported_spec_version", str(spec.get("spec_version")))
        return _normalize_params(spec.get("effective_params") or {})

    definition = (revision or {}).get("definition") or {}
    if not definition:
        raise ExtractFailure("execution_definition_missing")
    return _normalize_params(definition)


def _normalize_params(params: Dict[str, Any]) -> Dict[str, Any]:
    target = params["target"] if "target" in params else "per_doc"
    if not isinstance(target, str) or target not in SUPPORTED_TARGETS:
        raise ExtractFailure("target_not_supported", str(target))
    strategy = params["extraction_strategy"] if "extraction_strategy" in params else FULL_DOCUMENT_STRATEGY
    if not isinstance(strategy, str) or strategy not in SUPPORTED_STRATEGIES:
        raise ExtractFailure("strategy_invalid", str(strategy))
    if strategy == PAGE_ROUTED_STRATEGY and target != "per_doc":
        raise ExtractFailure("strategy_target_not_supported", f"{strategy}/{target}")
    if "data_schema" not in params:
        raise ExtractFailure("schema_missing", "缺少 data_schema；不再支持 fields 回退")
    schema = params["data_schema"]
    if not isinstance(schema, dict):
        raise ExtractFailure("schema_invalid", "data_schema 必须是 JSON 对象")
    errors = check_schema(schema)
    if errors:
        raise ExtractFailure("schema_invalid", errors[0])
    return {
        "target": target,
        "data_schema": schema,
        "schema_source": "data_schema",
        "extraction_strategy": strategy,
    }


def ensure_extract_strategy_available(spec: Dict[str, Any]) -> None:
    """Reject advanced execution explicitly; never silently run full_document."""
    if spec.get("extraction_strategy") == PAGE_ROUTED_STRATEGY:
        if not settings.EXTRACT_PAGE_ROUTED_ENABLED:
            raise ExtractFailure("strategy_unavailable", PAGE_ROUTED_STRATEGY)




def plan_units(target: str, parse_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """按 target 生成执行单元（顺序即源顺序）。"""
    pages = parse_data.get("pages") or []
    if target == "per_doc":
        source = str(parse_data.get("markdown") or "")
        if not source.strip():
            source = "\n\n".join(page_source(page) for page in pages)
        return [{"id": "doc", "label": "整份文档", "source": source}]

    return [
        {
            "id": f"p{page.get('page_no')}",
            "label": f"第 {page.get('page_no')} 页",
            "source": page_source(page),
        }
        for page in pages
    ]


def page_source(page: Dict[str, Any]) -> str:
    markdown = page.get("markdown")
    markdown_text = str(markdown).strip() if isinstance(markdown, str) else ""
    parts: List[str] = [markdown_text] if markdown_text else []
    for block in page.get("blocks") or []:
        text = str(block.get("text") or "").strip()
        table = str(block.get("table_html") or "").strip()
        latex = str(block.get("latex") or "").strip()
        for value in (text, table, latex):
            if value and value not in markdown_text and value not in parts:
                parts.append(value)
    return "\n".join(parts)


def assemble(target: str, outputs: List[Any]) -> Any:
    if target == "per_doc":
        return outputs[0] if outputs else {}
    return list(outputs)


def validate_output(target: str, schema: Dict[str, Any], payload: Any) -> List[Dict[str, str]]:
    """最终形状校验：per_doc → 单对象；per_page → 对象数组。"""
    if target == "per_doc":
        return validate_value(schema, payload)
    if not isinstance(payload, list):
        return [{"json_path": "$", "message": "per_page 结果必须是数组"}]
    issues: List[Dict[str, str]] = []
    for index, item in enumerate(payload):
        for issue in validate_value(schema, item):
            issues.append(
                {"json_path": f"$[{index}]{issue['json_path'][1:]}", "message": issue["message"]}
            )
    return issues


def classify_finish(reason: Optional[str]) -> str:
    if reason is None or reason == "":
        return "unknown"
    if reason == "stop":
        return "ok"
    if reason in ("length", "max_tokens"):
        return "truncated"
    if reason == "content_filter":
        return "filtered"
    return "unknown"


def _parse_deadline(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _remaining_seconds(deadline: Optional[datetime]) -> Optional[float]:
    if deadline is None:
        return None
    return (deadline - datetime.now(timezone.utc)).total_seconds()


async def _heartbeat_until(
    stop: asyncio.Event,
    lost: asyncio.Event,
    *,
    job_id: str,
    worker_id: str,
    attempts: int,
    interval: float,
) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            return
        except asyncio.TimeoutError:
            pass
        try:
            renewed = await renew_job_claim(job_id, worker_id, attempts)
        except Exception as exc:
            logger.opt(exception=exc).error(
                f"Extract 心跳续租异常，认领状态不可信: job_id={job_id}"
            )
            lost.set()
            return
        if not renewed:
            logger.warning(f"Extract 心跳续租失败，认领已失效: job_id={job_id}")
            lost.set()
            return


def _validate_binding_row(
    row: Dict[str, Any],
    job: Dict[str, Any],
    document: Dict[str, Any],
    tenant_id: str,
) -> None:
    document_ids = [str(item) for item in (job.get("document_ids") or []) if item]
    if (
        len(document_ids) != 1
        or str(row.get("document_id") or "") != document_ids[0]
        or row.get("sample_key") != "parse"
        or str(row.get("tenant_id") or "") != str(tenant_id)
    ):
        raise ExtractFailure("input_binding_invalid")


async def _load_bound_result(
    result_id: str,
    job: Dict[str, Any],
    document: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    row = await result_service.get_result(result_id)
    if not row:
        raise ExtractFailure("input_binding_lost")
    _validate_binding_row(row, job, document, tenant_id)
    return row


async def _reload_claimed_job(
    job_id: str,
    worker_id: str,
    attempts: int,
    lost: asyncio.Event,
) -> Dict[str, Any]:
    """回读 Job 并确认仍持有认领；不满足则标记失锁并抛 claim_lost。"""
    fresh = await get_job(job_id)
    if (
        not fresh
        or fresh.get("locked_by") != worker_id
        or int(fresh.get("attempts") or 0) != attempts
        or fresh.get("status") != "processing"
    ):
        lost.set()
        raise ExtractFailure("claim_lost")
    return fresh


async def _bind_with_recovery(
    job_id: str,
    worker_id: str,
    attempts: int,
    result_id: str,
) -> Optional[str]:
    """绑定 RPC 响应不确定时：先回读 Job 确认，再重试同一绑定一次。"""
    try:
        return await bind_extract_parse_result(job_id, worker_id, attempts, result_id)
    except Exception as exc:
        logger.opt(exception=exc).warning(
            f"Extract 绑定响应不确定，回读确认: job_id={job_id}"
        )

    fresh = await get_job(job_id)
    if fresh and fresh.get("parse_result_id"):
        return "bound_existing"

    try:
        return await bind_extract_parse_result(job_id, worker_id, attempts, result_id)
    except Exception as exc:
        raise ExtractFailure("binding_unconfirmed", str(exc)) from exc


async def ensure_parse_binding(
    job: Dict[str, Any],
    document: Dict[str, Any],
    *,
    worker_id: str,
    attempts: int,
    tenant_id: str,
    lost: asyncio.Event,
) -> Dict[str, Any]:
    """首次绑定 ParseResult（写一次）；重试只读绑定，回退即失败。"""
    job_id = str(job.get("job_id"))
    bound_id = job.get("parse_result_id")
    if bound_id:
        return await _load_bound_result(str(bound_id), job, document, tenant_id)

    row = await result_service.get_document_parse_result(document["id"], tenant_id=tenant_id)
    if not row:
        parsed = await ensure_parse_result(
            document_id=document["id"],
            file_path=document.get("file_path") or "",
            tenant_id=tenant_id,
        )
        if parsed:
            row = await result_service.get_document_parse_result(
                document["id"], tenant_id=tenant_id
            )
    if not row:
        raise ExtractFailure("parse_result_unavailable")

    _validate_binding_row(row, job, document, tenant_id)

    status = await _bind_with_recovery(job_id, worker_id, attempts, str(row["id"]))
    if status == "bound":
        return row

    fresh = await _reload_claimed_job(job_id, worker_id, attempts, lost)
    existing_id = fresh.get("parse_result_id")
    if existing_id:
        return await _load_bound_result(str(existing_id), fresh, document, tenant_id)
    raise ExtractFailure("binding_rejected")


def _escape_pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _unescape_pointer_token(value: str) -> str:
    return value.replace("~1", "/").replace("~0", "~")


def _schema_leaves(schema: Dict[str, Any], path: str = "") -> List[Tuple[str, Dict[str, Any]]]:
    properties = schema.get("properties")
    if isinstance(properties, dict) and properties:
        leaves: List[Tuple[str, Dict[str, Any]]] = []
        for key, child in properties.items():
            if isinstance(child, dict):
                child_path = f"{path}/{_escape_pointer_token(str(key))}"
                leaves.extend(_schema_leaves(child, child_path))
        return leaves
    if path:
        return [(path, schema)]
    return []


def _schema_at_pointer(schema: Dict[str, Any], pointer: str) -> Dict[str, Any]:
    node: Any = schema
    tokens = [token for token in pointer.split("/") if token]
    for token in tokens:
        key = _unescape_pointer_token(token)
        if not isinstance(node, dict):
            return {}
        node = (node.get("properties") or {}).get(key)
    return node if isinstance(node, dict) else {}


def _path_is_required(schema: Dict[str, Any], pointer: str) -> bool:
    node: Any = schema
    tokens = [_unescape_pointer_token(token) for token in pointer.split("/") if token]
    for token in tokens:
        if not isinstance(node, dict):
            return False
        required = node.get("required") or []
        if token not in required:
            return False
        node = (node.get("properties") or {}).get(token)
    return True


def _get_pointer(value: Any, pointer: str) -> Tuple[bool, Any]:
    current = value
    for token in [token for token in pointer.split("/") if token]:
        key = _unescape_pointer_token(token)
        if not isinstance(current, dict) or key not in current:
            return False, None
        current = current[key]
    return True, current


def _set_pointer(value: Dict[str, Any], pointer: str, item: Any) -> None:
    tokens = [_unescape_pointer_token(token) for token in pointer.split("/") if token]
    if not tokens:
        raise ExtractFailure("routed_write_path_invalid", pointer)
    current = value
    for token in tokens[:-1]:
        child = current.get(token)
        if not isinstance(child, dict):
            child = {}
            current[token] = child
        current = child
    current[tokens[-1]] = item


def _field_query(path: str, node: Dict[str, Any]) -> str:
    enum = node.get("enum")
    enum_text = " ".join(str(item) for item in enum) if isinstance(enum, list) else ""
    return " ".join(part for part in (path, node.get("description", ""), enum_text) if part)


def _routed_source(parse_data: Dict[str, Any], page_numbers: Sequence[int]) -> Tuple[str, Dict[int, Dict[str, Any]]]:
    wanted = set(int(page) for page in page_numbers)
    lines: List[str] = []
    refs: Dict[int, Dict[str, Any]] = {}
    pages = sorted(
        (page for page in (parse_data.get("pages") or []) if int(page.get("page_no") or 0) in wanted),
        key=lambda page: int(page.get("page_no") or 0),
    )
    for page in pages:
        page_no = int(page.get("page_no"))
        page_lines = [f"[[physical_page:{page_no}]]"]
        lines.extend(page_lines)
        page_blocks: Dict[str, str] = {}
        markdown = page.get("markdown")
        if isinstance(markdown, str) and markdown.strip():
            page_lines.append(markdown.strip())
            lines.append(markdown.strip())
        for block in sorted(page.get("blocks") or [], key=lambda item: item.get("reading_order", 0)):
            block_id = str(block.get("id") or "")
            values = [
                str(block.get("text") or "").strip(),
                str(block.get("table_html") or "").strip(),
                str(block.get("latex") or "").strip(),
            ]
            block_text = "\n".join(value for value in values if value)
            if not block_text:
                continue
            if block_id:
                page_blocks[block_id] = block_text
                marker = f"[[physical_page:{page_no} block:{block_id}]]"
                page_lines.append(marker)
                lines.append(marker)
            page_lines.append(block_text)
            lines.append(block_text)
        refs[page_no] = {"text": "\n".join(page_lines), "blocks": page_blocks}
    return "\n".join(lines), refs


def _evidence_refs(evidence: Any, path: str) -> List[Dict[str, Any]]:
    if not isinstance(evidence, dict):
        return []
    refs = evidence.get(path)
    if isinstance(refs, dict):
        return [refs]
    if isinstance(refs, list):
        return [ref for ref in refs if isinstance(ref, dict)]
    return []


def _value_paths(value: Any, path: str = "") -> List[str]:
    """Return leaf JSON-pointer paths while treating arrays as atomic values."""
    if isinstance(value, dict):
        paths: List[str] = []
        for key, child in value.items():
            child_path = f"{path}/{_escape_pointer_token(str(key))}"
            paths.extend(_value_paths(child, child_path))
        return paths or ([path] if path else [])
    return [path] if path else []


def _direct_value_supported(node: Dict[str, Any], value: Any, quote: str) -> bool:
    """Apply only deterministic support checks; semantic paraphrases remain model-judged."""
    if isinstance(value, (dict, list)):
        return True
    if node.get("format") == "date" or isinstance(value, (int, float)) or (
        isinstance(value, str) and any(char.isdigit() for char in value)
    ):
        value_digits = "".join(char for char in str(value) if char.isdigit())
        quote_digits = "".join(char for char in quote if char.isdigit())
        if value_digits:
            return value_digits in quote_digits
    return True


def _validate_candidate_values(
    schema: Dict[str, Any],
    values: Any,
    evidence: Any,
    allowed_paths: Sequence[str],
    page_refs: Dict[int, Dict[str, Any]],
    locked: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if not isinstance(values, dict):
        raise ExtractFailure("routed_values_invalid")
    accepted: Dict[str, Any] = {}
    accepted_evidence: Dict[str, Any] = {}
    allowed = set(allowed_paths)
    known = {path for path, _ in _schema_leaves(schema)}
    for value_path in _value_paths(values):
        if value_path in known:
            continue
        if any(path.startswith(value_path + "/") for path in known):
            continue
        raise ExtractFailure("routed_write_path_invalid", value_path)
    for path, node in _schema_leaves(schema):
        if path not in allowed:
            continue
        present, candidate = _get_pointer(values, path)
        if not present:
            continue
        refs = _evidence_refs(evidence, path)
        valid_refs: List[Dict[str, Any]] = []
        for ref in refs:
            try:
                page_no = int(ref.get("page_no"))
            except (TypeError, ValueError):
                continue
            page = page_refs.get(page_no)
            if not page:
                continue
            quote = str(ref.get("quote") or "").strip()
            if not quote:
                continue
            block_id = str(ref.get("block_id") or "")
            if block_id and block_id not in page.get("blocks", {}):
                continue
            haystack = (
                str(page.get("blocks", {}).get(block_id) or "")
                if block_id
                else str(page.get("text") or "")
            )
            if quote and " ".join(quote.split()) not in " ".join(haystack.split()):
                continue
            if not _direct_value_supported(node, candidate, quote):
                continue
            valid_refs.append({"page_no": page_no, "block_id": block_id or None, "quote": quote})
        if not valid_refs:
            continue
        issues = validate_value(node, candidate)
        if issues:
            continue
        if path in locked and locked[path] != candidate:
            raise ExtractFailure("field_conflict", path)
        accepted[path] = candidate
        accepted_evidence[path] = valid_refs
    return accepted, accepted_evidence


async def _routed_pass(
    *,
    messages: List[Dict[str, str]],
    allowed_paths: Sequence[str],
    job_id: str,
    worker_id: str,
    attempts: int,
    lost: asyncio.Event,
    deadline: Optional[datetime],
    request_gate: Callable[[str], Awaitable[None]],
    calls: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    repair_sent = False
    protocol_retry_used = False
    budget_left = MAX_REQUESTS_PER_UNIT
    while True:
        _ensure_execution_window(lost, deadline, "routed_pass")
        if budget_left <= 0:
            raise ExtractFailure("routed_pass_budget_exhausted")
        await request_gate("extract_pass")
        budget_left -= 1
        remaining = _remaining_seconds(deadline)
        try:
            result = await _await_with_deadline(
                invoke_llm(
                    messages,
                    json_mode=True,
                    max_output_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
                    timeout=remaining,
                ),
                deadline,
            )
        except asyncio.TimeoutError as exc:
            raise ExtractFailure("deadline_exceeded", "routed_pass") from exc
        except Exception as exc:
            if not _is_retryable_transport_error(exc) or repair_sent or budget_left <= 0:
                raise ExtractFailure("request_failed", f"routed_pass: {exc}") from exc
            continue

        calls.append({
            "unit": "routed_pass",
            "model": result.model,
            "finish_reason": result.finish_reason,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "request_id": result.request_id,
        })
        if result.refusal or result.content_invalid:
            raise ExtractFailure("response_content_invalid", "routed_pass")
        kind = classify_finish(result.finish_reason)
        if kind in ("truncated", "filtered"):
            raise ExtractFailure(f"response_{kind}", "routed_pass")
        if kind == "unknown":
            if protocol_retry_used or repair_sent or budget_left <= 0:
                raise ExtractFailure("completion_unknown", "routed_pass")
            protocol_retry_used = True
            continue
        try:
            envelope = strict_json_loads(result.content)
            if not isinstance(envelope, dict) or not isinstance(envelope.get("values"), dict):
                raise StrictJSONError("page-routed response must contain values object")
            return envelope["values"], envelope.get("evidence") or {}
        except StrictJSONError as exc:
            if repair_sent or budget_left <= 0:
                raise ExtractFailure("invalid_routed_json", str(exc)) from exc
            messages = build_repair_messages(messages, result.content, [{"json_path": "$", "message": str(exc)}])
            repair_sent = True
            _ensure_unit_fits(messages, "routed_pass")


def _embedding_profile() -> EmbeddingProfile:
    return EmbeddingProfile(
        model=settings.EMBEDDING_MODEL,
        dimension=settings.EMBEDDING_DIMENSION or None,
        query_instruction=settings.EMBEDDING_QUERY_INSTRUCTION,
        document_instruction=settings.EMBEDDING_DOCUMENT_INSTRUCTION,
        normalize=settings.EMBEDDING_NORMALIZE,
        version=settings.EMBEDDING_PROFILE_VERSION,
    )


async def _run_page_routed(
    *,
    spec: Dict[str, Any],
    parse_row: Dict[str, Any],
    tenant_id: str,
    document_id: str,
    job_id: str,
    worker_id: str,
    attempts: int,
    lost: asyncio.Event,
    deadline: Optional[datetime],
) -> Tuple[Any, Dict[str, Any], List[Dict[str, Any]], Dict[str, int]]:
    """Run the bounded page-routed strategy on one complete bound ParseResult."""
    usage: Dict[str, int] = {"requests": 0}

    async def request_gate(stage: str) -> None:
        _ensure_execution_window(lost, deadline, stage)
        try:
            consumed = await _await_with_deadline(
                consume_extract_request(job_id, worker_id, attempts), deadline
            )
        except asyncio.TimeoutError as exc:
            raise ExtractFailure("deadline_exceeded", stage) from exc
        if not consumed.get("allowed"):
            raise ExtractFailure(
                f"budget_{consumed.get('reason') or 'denied'}", stage
            )
        used = consumed.get("requests_used")
        usage["requests"] = int(used) if isinstance(used, int) else usage["requests"] + 1

    profile = _embedding_profile()
    try:
        snapshot = await page_index_service.ensure_index(
            parse_row,
            tenant_id=tenant_id,
            document_id=document_id,
            embedding_profile=profile,
            request_gate=request_gate,
        )
    except PageIndexError as exc:
        raise ExtractFailure(exc.reason, exc.message) from exc

    schema = spec["data_schema"]
    leaves = _schema_leaves(schema)
    unresolved = [path for path, _ in leaves]
    locked: Dict[str, Any] = {}
    evidence_by_path: Dict[str, Any] = {}
    selected_pages: set[int] = set()
    calls: List[Dict[str, Any]] = []
    pass_count = 0
    parse_data = parse_row.get("data") or {}

    while unresolved and pass_count < 2:
        pass_count += 1
        candidates_by_path: Dict[str, List[PageCandidate]] = {}
        for path, node in leaves:
            if path not in unresolved:
                continue
            try:
                candidates_by_path[path] = await page_index_service.retrieve(
                    snapshot,
                    query=_field_query(path, node),
                    embedding_profile=profile,
                    top_k=settings.PAGE_ROUTED_TOP_K,
                    neighbor_pages=settings.PAGE_ROUTED_NEIGHBOR_PAGES,
                    max_pages=settings.PAGE_ROUTED_MAX_PAGES,
                    request_gate=request_gate,
                )
            except PageIndexError as exc:
                raise ExtractFailure(exc.reason, exc.message) from exc
            selected_pages.update(candidate.page_no for candidate in candidates_by_path[path])

        if not selected_pages:
            break
        selected_pages = set(sorted(selected_pages)[: settings.PAGE_ROUTED_MAX_PAGES])
        source_text, page_refs = _routed_source(parse_data, sorted(selected_pages))
        if not source_text.strip():
            break
        messages = build_routed_messages(
            schema=schema,
            target="per_doc",
            source_text=source_text,
            allowed_paths=unresolved,
            unit_label=f"page-routed pass {pass_count}",
        )
        _ensure_unit_fits(messages, f"routed-pass-{pass_count}")
        values, pass_evidence = await _routed_pass(
            messages=messages,
            allowed_paths=unresolved,
            job_id=job_id,
            worker_id=worker_id,
            attempts=attempts,
            lost=lost,
            deadline=deadline,
            request_gate=request_gate,
            calls=calls,
        )

        # A locked path may be repeated as a read-only anchor, but a changed value is a conflict.
        for path in set(locked).intersection(path for path, _ in leaves):
            present, value = _get_pointer(values, path)
            if present and value != locked[path]:
                raise ExtractFailure("field_conflict", path)

        accepted, accepted_evidence = _validate_candidate_values(
            schema,
            values,
            pass_evidence,
            unresolved,
            page_refs,
            locked,
        )
        if not accepted:
            continue
        locked.update(accepted)
        evidence_by_path.update(accepted_evidence)
        unresolved = [path for path, _ in leaves if path not in locked]

    payload: Dict[str, Any] = {}
    for path, value in locked.items():
        _set_pointer(payload, path, value)
    for path, node in leaves:
        if path in locked or not _path_is_required(schema, path):
            continue
        if not validate_value(node, None):
            _set_pointer(payload, path, None)
    final_errors = validate_output("per_doc", schema, payload)
    if final_errors:
        raise ExtractFailure("final_validation_failed", str(final_errors[0]))
    routed_meta = {
        "parse_result_id": str(parse_row.get("id")),
        "passes": pass_count,
        "selected_pages": sorted(selected_pages),
        "evidence": evidence_by_path,
        "unresolved": unresolved,
        "index_profile": snapshot.embedding_profile_hash,
    }
    if len(json.dumps(routed_meta, ensure_ascii=False).encode("utf-8")) > ENGINE_MAX_BYTES // 2:
        raise ExtractFailure("evidence_limit_exceeded")
    return payload, routed_meta, calls, usage


def _ensure_unit_fits(messages: List[Dict[str, str]], unit_id: str) -> None:
    prompt_text = "\n".join(item.get("content") or "" for item in messages)
    if not fits_context(
        prompt_text,
        context_window=settings.LLM_CONTEXT_WINDOW_TOKENS,
        max_output_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
    ):
        raise ExtractFailure("context_exceeded", unit_id)


def _ensure_execution_window(
    lost: asyncio.Event,
    deadline: Optional[datetime],
    unit_id: str,
) -> Optional[float]:
    if lost.is_set():
        raise ExtractFailure("claim_lost")
    remaining = _remaining_seconds(deadline)
    if remaining is not None and remaining <= 0:
        raise ExtractFailure("deadline_exceeded", unit_id)
    return remaining


async def _await_with_deadline(
    awaitable: Awaitable[Any], deadline: Optional[datetime]
) -> Any:
    remaining = _remaining_seconds(deadline)
    if remaining is None:
        return await awaitable
    if remaining <= 0:
        close = getattr(awaitable, "close", None)
        if close is not None:
            close()
        raise asyncio.TimeoutError
    return await asyncio.wait_for(awaitable, timeout=remaining)


def _is_retryable_transport_error(error: Exception) -> bool:
    """只把网络/超时/限流/服务端错误纳入本单元的请求预算重试。"""
    if isinstance(
        error,
        (
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
            APIConnectionError,
            APITimeoutError,
            RateLimitError,
            InternalServerError,
        ),
    ):
        return True
    if isinstance(error, APIStatusError):
        status_code = error.status_code
        return status_code in {408, 429} or (
            isinstance(status_code, int) and status_code >= 500
        )
    status_code = getattr(error, "status_code", None)
    return status_code in {408, 429} or (
        isinstance(status_code, int) and status_code >= 500
    )


async def _run_unit(
    *,
    unit: Dict[str, Any],
    target: str,
    schema: Dict[str, Any],
    job_id: str,
    worker_id: str,
    attempts: int,
    lost: asyncio.Event,
    calls: List[Dict[str, Any]],
    usage: Dict[str, int],
    deadline: datetime,
) -> Any:
    messages = build_extract_messages(
        schema=schema,
        target=target,
        source_text=unit["source"],
        unit_label=unit["label"],
    )
    _ensure_unit_fits(messages, unit["id"])

    budget_left = MAX_REQUESTS_PER_UNIT
    repair_sent = False
    protocol_retry_used = False

    while True:
        remaining = _ensure_execution_window(lost, deadline, unit["id"])
        if budget_left <= 0:
            raise ExtractFailure("unit_failed", unit["id"])

        try:
            consumed = await _await_with_deadline(
                consume_extract_request(job_id, worker_id, attempts), deadline
            )
        except asyncio.TimeoutError as exc:
            raise ExtractFailure("deadline_exceeded", unit["id"]) from exc
        remaining = _ensure_execution_window(lost, deadline, unit["id"])
        if not consumed.get("allowed"):
            raise ExtractFailure(
                f"budget_{consumed.get('reason') or 'denied'}", unit["id"]
            )
        budget_left -= 1
        used = consumed.get("requests_used")
        usage["requests"] = int(used) if isinstance(used, int) else usage["requests"] + 1

        try:
            result: LLMResult = await _await_with_deadline(
                invoke_llm(
                    messages,
                    json_mode=True,
                    max_output_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
                    timeout=remaining,
                ),
                deadline,
            )
        except asyncio.TimeoutError as exc:
            raise ExtractFailure("deadline_exceeded", unit["id"]) from exc
        except Exception as exc:
            if (
                not _is_retryable_transport_error(exc)
                or repair_sent
                or budget_left <= 0
            ):
                raise ExtractFailure("request_failed", f"{unit['id']}: {exc}") from exc
            logger.warning(f"Extract 请求异常，额度内重试: unit={unit['id']} error={exc}")
            continue

        _ensure_execution_window(lost, deadline, unit["id"])

        calls.append(
            {
                "unit": unit["id"],
                "model": result.model,
                "finish_reason": result.finish_reason,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "request_id": result.request_id,
            }
        )

        if result.refusal:
            raise ExtractFailure("response_refused", unit["id"])
        if result.content_invalid:
            raise ExtractFailure("response_content_invalid", unit["id"])

        kind = classify_finish(result.finish_reason)
        if kind == "truncated":
            raise ExtractFailure("response_truncated", unit["id"])
        if kind == "filtered":
            raise ExtractFailure("response_filtered", unit["id"])
        if kind == "unknown":
            if protocol_retry_used or repair_sent or budget_left <= 0:
                raise ExtractFailure("completion_unknown", unit["id"])
            protocol_retry_used = True
            continue

        try:
            value = strict_json_loads(result.content)
        except StrictJSONError as exc:
            if repair_sent or budget_left <= 0:
                raise ExtractFailure("invalid_json", f"{unit['id']}: {exc}") from exc
            messages = build_repair_messages(
                messages, result.content, [{"json_path": "$", "message": str(exc)}]
            )
            repair_sent = True
            _ensure_unit_fits(messages, unit["id"])
            continue

        errors = validate_value(schema, value)
        if errors:
            if repair_sent or budget_left <= 0:
                raise ExtractFailure("schema_validation_failed", f"{unit['id']}: {errors[0]}")
            messages = build_repair_messages(messages, result.content, errors)
            repair_sent = True
            _ensure_unit_fits(messages, unit["id"])
            continue

        return value


async def _run_units(
    *,
    units: List[Dict[str, Any]],
    target: str,
    schema: Dict[str, Any],
    job_id: str,
    worker_id: str,
    attempts: int,
    lost: asyncio.Event,
    usage: Dict[str, int],
    deadline: datetime,
) -> Tuple[List[Any], List[Dict[str, Any]]]:
    outputs: List[Any] = []
    calls: List[Dict[str, Any]] = []
    for unit in units:
        if lost.is_set():
            raise ExtractFailure("claim_lost")
        outputs.append(
            await _run_unit(
                unit=unit,
                target=target,
                schema=schema,
                job_id=job_id,
                worker_id=worker_id,
                attempts=attempts,
                lost=lost,
                calls=calls,
                usage=usage,
                deadline=deadline,
            )
        )
    return outputs, calls


def _sum_tokens(calls: List[Dict[str, Any]], field: str) -> Optional[int]:
    values = [item.get(field) for item in calls]
    if not calls or any(not isinstance(value, int) for value in values):
        return None
    return sum(values)


def build_engine(
    spec: Dict[str, Any],
    calls: List[Dict[str, Any]],
    attempts: int,
    requests: Optional[int] = None,
    page_routed: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    engine: Dict[str, Any] = {
        "name": "neoflow-extract",
        "target": spec["target"],
        "extraction_strategy": spec.get("extraction_strategy", FULL_DOCUMENT_STRATEGY),
        "schema_hash": schema_hash(spec["data_schema"]),
        "schema_source": spec["schema_source"],
        "prompt_version": "v1",
        "attempts": attempts,
        "usage": {
            "requests": requests if requests is not None else len(calls),
            "input_tokens": _sum_tokens(calls, "input_tokens"),
            "output_tokens": _sum_tokens(calls, "output_tokens"),
            "calls": calls[:ENGINE_MAX_CALLS],
        },
    }
    if requests is not None and requests != len(calls):
        engine["usage"]["input_tokens"] = None
        engine["usage"]["output_tokens"] = None
    if page_routed is not None:
        engine["page_routed"] = page_routed
    serialized = json.dumps(engine, ensure_ascii=False).encode("utf-8")
    while len(serialized) > ENGINE_MAX_BYTES and engine["usage"]["calls"]:
        engine["usage"]["calls"] = engine["usage"]["calls"][:-1]
        serialized = json.dumps(engine, ensure_ascii=False).encode("utf-8")
    if len(serialized) > ENGINE_MAX_BYTES:
        raise ExtractFailure("engine_metadata_too_large")
    return engine


async def _fetch_extract_result(job_id: str) -> Optional[Dict[str, Any]]:
    rows = await result_service.list_results(
        job_id=job_id,
        sample_key=EXTRACT_SAMPLE_KEY,
        limit=1,
    )
    return rows[0] if rows else None


async def _submit_success(
    job_id: str,
    worker_id: str,
    attempts: int,
    payload: Any,
    engine: Dict[str, Any],
) -> Optional[str]:
    return await commit_extract_job(
        job_id,
        worker_id,
        attempts,
        "ok",
        extract_data=payload,
        engine=engine,
    )


async def _read_confirmed_success(job_id: str) -> Optional[Any]:
    fresh = await get_job(job_id)
    existing = await _fetch_extract_result(job_id)
    if fresh and fresh.get("status") == "completed" and existing:
        return existing.get("data")
    return None


async def _commit_failure(
    job_id: str,
    worker_id: str,
    attempts: int,
    failure: ExtractFailure,
) -> None:
    message = f"{failure.reason}: {failure.message}".strip(": ")
    try:
        await commit_extract_job(job_id, worker_id, attempts, "failed", error=message)
    except Exception as exc:
        logger.opt(exception=exc).error(f"Extract 失败交卷异常: job_id={job_id}")


async def _commit_success(
    job_id: str,
    worker_id: str,
    attempts: int,
    payload: Any,
    engine: Dict[str, Any],
) -> Any:
    """成功交卷；响应丢失时回读确认或重试同一交卷，绝不盲目标失败。"""
    try:
        status = await _submit_success(job_id, worker_id, attempts, payload, engine)
    except Exception as exc:
        logger.opt(exception=exc).warning(
            f"Extract 交卷响应不确定，回读确认: job_id={job_id}"
        )
        try:
            confirmed = await _read_confirmed_success(job_id)
        except Exception as confirm_exc:
            logger.opt(exception=confirm_exc).error(
                f"Extract 交卷确认读取失败，保持不确定状态: job_id={job_id}"
            )
            return None
        if confirmed is not None:
            return confirmed
        try:
            status = await _submit_success(job_id, worker_id, attempts, payload, engine)
        except Exception as retry_exc:
            logger.opt(exception=retry_exc).error(
                f"Extract 交卷仍不确定，交由重领兜底: job_id={job_id}"
            )
            return None

    if status == "completed":
        return payload
    if status == "already_committed":
        try:
            existing = await _fetch_extract_result(job_id)
        except Exception as confirm_exc:
            logger.opt(exception=confirm_exc).error(
                f"Extract 已交卷但 Result 回读失败，保持不确定状态: job_id={job_id}"
            )
            return None
        return existing.get("data") if existing else None
    if status in ("stale", "stale_token", "not_found"):
        logger.warning(f"Extract 交卷未生效: job_id={job_id} status={status}")
        return None
    raise ExtractFailure("commit_rejected", str(status))


async def handle_extract_job(
    job: Dict[str, Any],
    revision: Optional[Dict[str, Any]] = None,
    configuration: Optional[Dict[str, Any]] = None,
) -> Any:
    """JobRunner 的 Extract handler。"""
    job_id = str(job.get("job_id") or "")
    worker_id = job.get("locked_by")
    attempts = int(job.get("attempts") or 0)
    if not job_id or not worker_id or attempts <= 0:
        logger.error(
            "Extract Job 缺少认领信息，跳过执行且不写终态: "
            f"job_id={job_id} worker={worker_id} attempts={attempts}"
        )
        return None

    if attempts > settings.EXTRACT_MAX_ATTEMPTS:
        await _commit_failure(
            job_id, worker_id, attempts,
            ExtractFailure("attempts_exceeded", f"attempts={attempts}"),
        )
        return None

    try:
        spec = resolve_extract_spec(job, revision, configuration)
        ensure_extract_strategy_available(spec)
        document_ids = [str(item) for item in (job.get("document_ids") or []) if item]
        if len(document_ids) != 1:
            raise ExtractFailure("document_count_invalid")
        document = await supabase_service.get_document(document_ids[0])
        if not document or not document.get("file_path"):
            raise ExtractFailure("document_unavailable")
        tenant_id = str(job.get("tenant_id") or document.get("tenant_id") or "")
        if not tenant_id:
            raise ExtractFailure("tenant_missing")

        budget = await ensure_extract_budget(
            job_id,
            worker_id,
            attempts,
            settings.EXTRACT_MAX_REQUESTS_PER_JOB,
            settings.EXTRACT_TIMEOUT_SECONDS,
        )
        if budget.get("status") in ("not_found", "stale_token"):
            raise ExtractFailure(f"budget_{budget.get('status')}")
        deadline = _parse_deadline(budget.get("deadline"))
        if deadline is None:
            raise ExtractFailure("budget_uninitialized")

        stop = asyncio.Event()
        lost = asyncio.Event()
        interval = max(30.0, float(settings.DOC_WORKER_STALE_LOCK_SECONDS) / 3.0)
        heartbeat = asyncio.create_task(
            _heartbeat_until(
                stop,
                lost,
                job_id=job_id,
                worker_id=worker_id,
                attempts=attempts,
                interval=interval,
            )
        )
        try:
            parse_row = await ensure_parse_binding(
                job,
                document,
                worker_id=worker_id,
                attempts=attempts,
                tenant_id=tenant_id,
                lost=lost,
            )
            if spec["extraction_strategy"] == PAGE_ROUTED_STRATEGY:
                payload, routed_meta, calls, usage = await _run_page_routed(
                    spec=spec,
                    parse_row=parse_row,
                    tenant_id=tenant_id,
                    document_id=document_ids[0],
                    job_id=job_id,
                    worker_id=worker_id,
                    attempts=attempts,
                    lost=lost,
                    deadline=deadline,
                )
                engine = build_engine(
                    spec, calls, attempts, usage["requests"], page_routed=routed_meta
                )
            else:
                units = plan_units(spec["target"], parse_row.get("data") or {})
                if not units:
                    raise ExtractFailure("no_units")
                usage = {"requests": 0}
                outputs, calls = await _run_units(
                    units=units,
                    target=spec["target"],
                    schema=spec["data_schema"],
                    job_id=job_id,
                    worker_id=worker_id,
                    attempts=attempts,
                    lost=lost,
                    usage=usage,
                    deadline=deadline,
                )
                payload = assemble(spec["target"], outputs)
                final_errors = validate_output(spec["target"], spec["data_schema"], payload)
                if final_errors:
                    raise ExtractFailure("final_validation_failed", str(final_errors[0]))
                engine = build_engine(spec, calls, attempts, usage["requests"])
            try:
                _ensure_execution_window(lost, deadline, "commit")
            except ExtractFailure:
                logger.warning(
                    f"Extract 认领或 deadline 已失效，跳过交卷: job_id={job_id}"
                )
                raise
            result = await _commit_success(job_id, worker_id, attempts, payload, engine)
        finally:
            stop.set()
            if not heartbeat.done():
                await heartbeat

        if result is not None:
            logger.info(
                f"Extract 完成: job_id={job_id} target={spec['target']} "
                f"schema_source={spec['schema_source']} requests={engine['usage']['requests']}"
            )
        return result
    except ExtractFailure as exc:
        logger.error(f"Extract 失败: job_id={job_id} reason={exc.reason} message={exc.message}")
        await _commit_failure(job_id, worker_id, attempts, exc)
        return None
    except Exception as exc:
        logger.opt(exception=exc).error(f"Extract 执行异常: job_id={job_id}")
        await _commit_failure(
            job_id, worker_id, attempts, ExtractFailure("internal_error", str(exc))
        )
        return None
