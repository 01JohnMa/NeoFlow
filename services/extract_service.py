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
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

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
    commit_extract_parse_result,
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
    fits_context,
    strict_json_loads,
)
from services.extract_schema import check_schema, schema_hash, validate_value
from services.business_validation import validate_template_values
from services.template_contract import is_canonical_schema, load_template
from services.agentic_source import AgenticSourceError, route_with_agent
from services.llm_invoke import LLMResult, invoke_llm
from services.parse_service import (
    annotate_parse_provenance,
    apply_parse_postprocess,
    build_parse_params,
)
from services.parser_adapter import get_parser_adapter
from services.source_page_index import (
    SourcePageIndexError,
    build_source_page_index,
    compact_page_ranges,
    retrieve_source_pages,
)
from services.result_service import result_service
from services.supabase_service import supabase_service

EXTRACT_CAPABILITY = "extract"
SPEC_VERSION = "1"
SUPPORTED_TARGETS = ("per_doc", "per_page")
FULL_DOCUMENT_STRATEGY = "full_document"
SOURCE_PAGE_ROUTED_STRATEGY = "source_page_routed"
AGENTIC_SOURCE_PAGE_ROUTED_STRATEGY = "agentic_source_page_routed"
SUPPORTED_STRATEGIES = (
    FULL_DOCUMENT_STRATEGY,
    SOURCE_PAGE_ROUTED_STRATEGY,
    AGENTIC_SOURCE_PAGE_ROUTED_STRATEGY,
)
MAX_REQUESTS_PER_UNIT = 3
ENGINE_MAX_BYTES = 16384
ENGINE_MAX_CALLS = 20
EXTRACT_SAMPLE_KEY = "extract"

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
    if strategy in {SOURCE_PAGE_ROUTED_STRATEGY, AGENTIC_SOURCE_PAGE_ROUTED_STRATEGY} and target != "per_doc":
        raise ExtractFailure(
            "strategy_target_not_supported",
            "source_page_routed/agentic_source_page_routed 只支持 per_doc",
        )
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


def validate_business_output(schema: Dict[str, Any], payload: Any) -> List[Dict[str, Any]]:
    """Run generic business-shape checks for the canonical template only.

    The validator is shape-driven; it does not know field names such as
    ``trial_phase`` or any document-specific business rule. Other arbitrary
    user schemas continue to use their JSON Schema contract alone.
    """
    if not is_canonical_schema(schema):
        return []
    if not isinstance(payload, dict):
        return [{"key": "$", "code": "invalid_payload", "message": "抽取结果必须是对象"}]
    return validate_template_values(load_template(), payload)


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
        or str(row.get("job_id") or "") != str(job.get("job_id") or "")
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


async def _commit_parse_result_with_recovery(
    *,
    job: Dict[str, Any],
    document: Dict[str, Any],
    tenant_id: str,
    parse_data: Dict[str, Any],
    parse_engine: Optional[Dict[str, Any]],
    worker_id: str,
    attempts: int,
    deadline: Optional[datetime],
) -> Dict[str, Any]:
    """Atomically save and bind this Job's ParseResult; recover lost replies."""
    job_id = str(job.get("job_id"))

    async def call_rpc() -> Dict[str, Any]:
        return await _await_with_deadline(
            commit_extract_parse_result(
                job_id,
                worker_id,
                attempts,
                parse_data,
                parse_engine,
            ),
            deadline,
        )

    try:
        response = await call_rpc()
    except Exception as exc:
        logger.opt(exception=exc).warning(
            f"Extract Parse 绑定响应不确定，回读确认: job_id={job_id}"
        )
        fresh = await get_job(job_id)
        if fresh and fresh.get("parse_result_id"):
            return await _load_bound_result(
                str(fresh["parse_result_id"]), fresh, document, tenant_id
            )
        try:
            response = await call_rpc()
        except Exception as retry_exc:
            raise ExtractFailure("binding_unconfirmed", str(retry_exc)) from retry_exc

    status = response.get("status")
    if status not in ("bound", "already_bound"):
        raise ExtractFailure(
            "binding_rejected",
            response.get("reason") or str(status),
        )
    result_id = response.get("result_id")
    if not result_id:
        raise ExtractFailure("binding_unconfirmed", "ParseResult id missing")
    return await _load_bound_result(str(result_id), job, document, tenant_id)


async def ensure_parse_binding(
    job: Dict[str, Any],
    document: Dict[str, Any],
    *,
    worker_id: str,
    attempts: int,
    tenant_id: str,
    lost: asyncio.Event,
    parse_params: Optional[Dict[str, Any]] = None,
    request_gate: Optional[Callable[[str], Awaitable[None]]] = None,
) -> Dict[str, Any]:
    """首次绑定 ParseResult（写一次）；重试只读绑定，回退即失败。"""
    job_id = str(job.get("job_id"))
    bound_id = job.get("parse_result_id")
    if bound_id:
        return await _load_bound_result(str(bound_id), job, document, tenant_id)

    # Extract owns its ParseResult. Never read the latest ParseResult for the
    # Document: another Configuration/Job may have produced a different input.
    params = dict(parse_params or build_parse_params())
    if request_gate:
        await request_gate("full_document_parse")
    try:
        parser = get_parser_adapter(params)
        parsed = await parser.parse(document["file_path"], params)
        if parsed is None:
            raise ExtractFailure("parse_result_unavailable")
        apply_parse_postprocess(parsed, params)
        annotate_parse_provenance(parsed, document["file_path"], params)
    except Exception as exc:
        raise ExtractFailure("parse_result_unavailable", str(exc)) from exc
    return await _commit_parse_result_with_recovery(
        job=job,
        document=document,
        tenant_id=tenant_id,
        parse_data=parsed.to_dict(),
        parse_engine=getattr(parsed, "engine", None),
        worker_id=worker_id,
        attempts=attempts,
        deadline=None,
    )


def _source_field_query(path: str, node: Dict[str, Any]) -> str:
    enum = node.get("enum")
    enum_text = " ".join(str(item) for item in enum) if isinstance(enum, list) else ""
    return " ".join(part for part in (path, node.get("description", ""), enum_text) if part)


async def _source_page_parse_and_bind(
    *,
    spec: Dict[str, Any],
    job: Dict[str, Any],
    document: Dict[str, Any],
    tenant_id: str,
    job_id: str,
    worker_id: str,
    attempts: int,
    lost: asyncio.Event,
    deadline: Optional[datetime],
    usage: Dict[str, int],
    parse_params: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    # A retry of the same Extract Job must reuse its own bound ParseResult.
    # A new Job intentionally arrives without parse_result_id and builds a new
    # source index/partial parse, even for the same Document.
    bound_id = job.get("parse_result_id")
    if bound_id:
        bound = await _load_bound_result(str(bound_id), job, document, tenant_id)
        return bound, {"reused_job_parse_result": True}

    async def request_gate(stage: str) -> None:
        _ensure_execution_window(lost, deadline, stage)
        try:
            consumed = await _await_with_deadline(
                consume_extract_request(job_id, worker_id, attempts), deadline
            )
        except asyncio.TimeoutError as exc:
            raise ExtractFailure("deadline_exceeded", stage) from exc
        if not consumed.get("allowed"):
            raise ExtractFailure(f"budget_{consumed.get('reason') or 'denied'}", stage)
        used = consumed.get("requests_used")
        usage["requests"] = int(used) if isinstance(used, int) else usage["requests"] + 1

    try:
        index = await build_source_page_index(
            document["file_path"], request_gate=request_gate
        )
        queries = {
            path: _source_field_query(path, node)
            for path, node in _schema_leaves(spec["data_schema"])
        }
        candidates = await retrieve_source_pages(
            index, queries=queries, request_gate=request_gate
        )
    except SourcePageIndexError as exc:
        raise ExtractFailure(exc.reason, exc.message) from exc

    selected = sorted({candidate.page_no for rows in candidates.values() for candidate in rows})
    if not selected:
        raise ExtractFailure("source_page_no_candidates")
    page_ranges = compact_page_ranges(selected)
    await request_gate("source_page_parse")
    base_parse_params = dict(parse_params or build_parse_params())
    parse_params = {
        **base_parse_params,
        "model_version": base_parse_params.get("model_version") or "pipeline",
        "page_ranges": page_ranges,
        "enable_table": True,
        "enable_formula": True,
    }
    try:
        parsed = await get_parser_adapter(parse_params).parse(document["file_path"], parse_params)
        if parsed is None:
            raise ExtractFailure("source_page_parse_result_unavailable")
        apply_parse_postprocess(parsed, parse_params)
        annotate_parse_provenance(parsed, document["file_path"], parse_params)
    except ExtractFailure:
        raise
    except Exception as exc:
        raise ExtractFailure("source_page_parse_failed", str(exc)) from exc
    bound = await _commit_parse_result_with_recovery(
        job=job,
        document=document,
        tenant_id=tenant_id,
        parse_data=parsed.to_dict(),
        parse_engine=getattr(parsed, "engine", None),
        worker_id=worker_id,
        attempts=attempts,
        deadline=deadline,
    )
    metadata = {
        "source_hash": index.source_hash,
        "selected_pages": selected,
        "page_ranges": page_ranges,
        "candidate_sources": {
            str(page): sorted({source for candidate in rows if candidate.page_no == page for source in (candidate.sources or candidate.reasons)})
            for page in selected
            for rows in candidates.values()
            if any(candidate.page_no == page for candidate in rows)
        },
        "modalities": {str(page.page_no): page.modality for page in index.pages if page.page_no in selected},
        "index_profile": index.profile,
    }
    return bound, metadata


async def _agentic_source_page_parse_and_bind(
    *,
    spec: Dict[str, Any],
    job: Dict[str, Any],
    document: Dict[str, Any],
    tenant_id: str,
    job_id: str,
    worker_id: str,
    attempts: int,
    lost: asyncio.Event,
    deadline: Optional[datetime],
    usage: Dict[str, int],
    parse_params: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Agentic routing with bounded search/Parse tools and one merged ParseResult."""
    bound_id = job.get("parse_result_id")
    if bound_id:
        bound = await _load_bound_result(str(bound_id), job, document, tenant_id)
        return bound, {"reused_job_parse_result": True}

    async def request_gate(stage: str) -> None:
        _ensure_execution_window(lost, deadline, stage)
        try:
            consumed = await _await_with_deadline(
                consume_extract_request(job_id, worker_id, attempts), deadline
            )
        except asyncio.TimeoutError as exc:
            raise ExtractFailure("deadline_exceeded", stage) from exc
        if not consumed.get("allowed"):
            raise ExtractFailure(f"budget_{consumed.get('reason') or 'denied'}", stage)
        used = consumed.get("requests_used")
        usage["requests"] = int(used) if isinstance(used, int) else usage["requests"] + 1

    try:
        index = await build_source_page_index(document["file_path"], request_gate=request_gate)
    except SourcePageIndexError as exc:
        raise ExtractFailure(exc.reason, exc.message) from exc

    async def parse_pages(page_numbers: List[int]):
        selected = sorted({int(page) for page in page_numbers if int(page) > 0})
        if not selected:
            raise AgenticSourceError("agent_empty_parse_pages")
        await request_gate("agentic_source_page_parse")
        base_params = dict(parse_params or build_parse_params())
        params = {
            **base_params,
            "model_version": base_params.get("model_version") or "pipeline",
            "page_ranges": compact_page_ranges(selected),
            "enable_table": True,
            "enable_formula": True,
        }
        try:
            parsed = await get_parser_adapter(params).parse(document["file_path"], params)
            if parsed is None:
                raise AgenticSourceError("agent_parse_result_unavailable")
            apply_parse_postprocess(parsed, params)
            annotate_parse_provenance(parsed, document["file_path"], params)
            return parsed
        except AgenticSourceError:
            raise
        except Exception as exc:
            raise AgenticSourceError(f"agent_parse_failed: {exc}") from exc

    remaining = _remaining_seconds(deadline)
    agent_deadline = None
    if remaining is not None:
        agent_deadline = asyncio.get_running_loop().time() + max(0.0, remaining)
    try:
        routed = await route_with_agent(
            index,
            spec["data_schema"],
            parse_pages,
            request_gate=request_gate,
            deadline=agent_deadline,
            max_search_tools=getattr(settings, "AGENTIC_MAX_SEARCH_TOOLS", 8),
            max_parse_calls=getattr(settings, "AGENTIC_MAX_PARSE_CALLS", 2),
            max_unique_pages=getattr(settings, "AGENTIC_MAX_UNIQUE_PAGES", 64),
            max_agent_turns=getattr(settings, "AGENTIC_MAX_TURNS", 16),
        )
    except AgenticSourceError as exc:
        raise ExtractFailure("agentic_source_failed", str(exc)) from exc

    all_pages = sorted({int(page.page_no) for page in routed.parse_result.pages})
    merged_params = {
        **(parse_params or build_parse_params()),
        "page_ranges": compact_page_ranges(all_pages),
    }
    annotate_parse_provenance(routed.parse_result, document["file_path"], merged_params)
    stats = routed.stats
    parse_engine = {
        **routed.parse_result.engine,
        "agentic_source_page_routed": {
            "searches": stats.searches,
            "parse_calls": stats.parse_calls,
            "llm_calls": stats.llm_calls,
            "agent_turns": stats.agent_turns,
            "unique_pages": stats.unique_pages,
            "trace": stats.trace[:16],
        },
    }
    bound = await _commit_parse_result_with_recovery(
        job=job,
        document=document,
        tenant_id=tenant_id,
        parse_data=routed.parse_result.to_dict(),
        parse_engine=parse_engine,
        worker_id=worker_id,
        attempts=attempts,
        deadline=deadline,
    )
    metadata = {
        **routed.route_metadata,
        "source_hash": index.source_hash,
        "selected_pages": all_pages,
        "page_ranges": compact_page_ranges(all_pages),
        "modalities": {
            str(page.page_no): page.modality
            for page in index.pages
            if page.page_no in all_pages
        },
        "index_profile": index.profile,
        "searches": stats.searches,
        "parse_calls": stats.parse_calls,
        "llm_calls": stats.llm_calls,
        "agent_turns": stats.agent_turns,
        "unique_pages": stats.unique_pages,
        "trace": stats.trace[:16],
    }
    return bound, metadata


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
        if not errors:
            business_issues = validate_business_output(schema, value)
            errors = [
                {
                    "json_path": f"$.{issue.get('key', '')}" if issue.get("key") else "$",
                    "message": str(issue.get("message") or issue.get("code") or "业务校验失败"),
                }
                for issue in business_issues
            ]
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
    source_page_routed: Optional[Dict[str, Any]] = None,
    agentic_source_page_routed: Optional[Dict[str, Any]] = None,
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
    if source_page_routed is not None:
        engine["source_page_routed"] = source_page_routed
    if agentic_source_page_routed is not None:
        engine["agentic_source_page_routed"] = agentic_source_page_routed
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
        document_ids = [str(item) for item in (job.get("document_ids") or []) if item]
        if len(document_ids) != 1:
            raise ExtractFailure("document_count_invalid")
        document = await supabase_service.get_document(document_ids[0])
        if not document or not document.get("file_path"):
            raise ExtractFailure("document_unavailable")
        tenant_id = str(job.get("tenant_id") or document.get("tenant_id") or "")
        if not tenant_id:
            raise ExtractFailure("tenant_missing")
        parse_params = build_parse_params(revision=revision, configuration=configuration)

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
            source_metadata: Optional[Dict[str, Any]] = None
            agentic_metadata: Optional[Dict[str, Any]] = None
            usage = {"requests": 0}

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
                usage["requests"] = (
                    int(used) if isinstance(used, int) else usage["requests"] + 1
                )

            if spec["extraction_strategy"] == AGENTIC_SOURCE_PAGE_ROUTED_STRATEGY:
                parse_row, agentic_metadata = await _agentic_source_page_parse_and_bind(
                    spec=spec,
                    job=job,
                    document=document,
                    tenant_id=tenant_id,
                    job_id=job_id,
                    worker_id=worker_id,
                    attempts=attempts,
                    lost=lost,
                    deadline=deadline,
                    usage=usage,
                    parse_params=parse_params,
                )
            elif spec["extraction_strategy"] == SOURCE_PAGE_ROUTED_STRATEGY:
                parse_row, source_metadata = await _source_page_parse_and_bind(
                    spec=spec,
                    job=job,
                    document=document,
                    tenant_id=tenant_id,
                    job_id=job_id,
                    worker_id=worker_id,
                    attempts=attempts,
                    lost=lost,
                    deadline=deadline,
                    usage=usage,
                    parse_params=parse_params,
                )
            else:
                parse_row = await ensure_parse_binding(
                    job,
                    document,
                    worker_id=worker_id,
                    attempts=attempts,
                    tenant_id=tenant_id,
                    lost=lost,
                    parse_params=parse_params,
                    request_gate=request_gate,
                )
            units = plan_units(spec["target"], parse_row.get("data") or {})
            if not units:
                raise ExtractFailure("no_units")
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
            if not final_errors and spec["target"] == "per_doc":
                final_errors = [
                    {
                        "json_path": f"$.{issue.get('key', '')}" if issue.get("key") else "$",
                        "message": str(issue.get("message") or issue.get("code") or "业务校验失败"),
                    }
                    for issue in validate_business_output(spec["data_schema"], payload)
                ]
            if final_errors:
                raise ExtractFailure("final_validation_failed", str(final_errors[0]))
            engine = build_engine(
                spec,
                calls,
                attempts,
                usage["requests"],
                source_page_routed=source_metadata,
                agentic_source_page_routed=agentic_metadata,
            )
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
