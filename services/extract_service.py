# services/extract_service.py
"""Extract handler：绑定 ParseResult → 单元执行 → 组装 → 认领感知原子交卷。

本轮（#32 v3.1 / ADR-0009）：
- target：per_doc（整文单实例）、per_page（逐页单实例，结果按页序数组）；
  per_table_row 明确拒绝；
- 整文直抽：超上下文明确失败，不截断、不做分块；
- 严格校验（JSON Schema 子集）失败最多修复一次；请求预算由单元执行器计数；
- 绑定写一次（写进 Job 的 parse_result_id），重试只读绑定。
"""

import asyncio
import json
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from api.jobs import (
    bind_extract_parse_result,
    commit_extract_job,
    consume_extract_request,
    ensure_extract_budget,
    get_job,
    renew_job_claim,
    update_job,
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
from services.llm_invoke import LLMResult, invoke_llm
from services.parse_service import ensure_parse_result
from services.result_service import result_service
from services.supabase_service import supabase_service

EXTRACT_CAPABILITY = "extract"
SPEC_VERSION = "1"
SUPPORTED_TARGETS = ("per_doc", "per_page")
MAX_REQUESTS_PER_UNIT = 3
ENGINE_MAX_BYTES = 16384
ENGINE_MAX_CALLS = 20

LEGACY_TYPE_MAP = {
    "text": {"type": "string"},
    "date": {"type": "string", "format": "date"},
    "number": {"type": "number"},
    "boolean": {"type": "boolean"},
}


class ExtractFailure(Exception):
    """可解释的执行失败（reason 进 Job error，不发正式结果）。"""

    def __init__(self, reason: str, message: str = ""):
        super().__init__(f"{reason}: {message}" if message else reason)
        self.reason = reason
        self.message = message


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
    target = params.get("target") or "per_doc"
    if target not in SUPPORTED_TARGETS:
        raise ExtractFailure("target_not_supported", str(target))

    schema = params.get("data_schema")
    schema_source = "data_schema"
    if not isinstance(schema, dict):
        fields = params.get("fields")
        if isinstance(fields, list) and fields:
            schema = legacy_fields_to_schema(fields)
            schema_source = "legacy_fields"
        else:
            raise ExtractFailure("schema_missing")

    errors = check_schema(schema)
    if errors:
        raise ExtractFailure("schema_invalid", errors[0])

    return {"target": target, "data_schema": schema, "schema_source": schema_source}


def legacy_fields_to_schema(fields: List[Dict[str, Any]]) -> Dict[str, Any]:
    """把旧扁平字段模型转成 JSON Schema（历史配置兼容执行视图）。"""
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for field in fields:
        key = str(field.get("field_key") or "").strip()
        if not key:
            continue
        spec = dict(LEGACY_TYPE_MAP.get(str(field.get("field_type") or "text"), {"type": "string"}))
        description = str(field.get("extraction_hint") or "").strip() or str(
            field.get("field_label") or key
        )
        spec["description"] = description
        properties[key] = spec
        if field.get("is_required"):
            required.append(key)

    schema: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


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
    if isinstance(markdown, str) and markdown.strip():
        return markdown

    parts: List[str] = []
    for block in page.get("blocks") or []:
        for field in ("text", "table_html", "latex"):
            value = block.get(field)
            if value:
                parts.append(str(value))
                break
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
        if not await renew_job_claim(job_id, worker_id, attempts):
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

    status = await bind_extract_parse_result(job_id, worker_id, attempts, str(row["id"]))
    if status == "bound":
        return row

    fresh = await get_job(job_id)
    if (
        not fresh
        or fresh.get("locked_by") != worker_id
        or int(fresh.get("attempts") or 0) != attempts
        or fresh.get("status") != "processing"
    ):
        lost.set()
        raise ExtractFailure("claim_lost")
    existing_id = fresh.get("parse_result_id")
    if existing_id:
        return await _load_bound_result(str(existing_id), fresh, document, tenant_id)
    raise ExtractFailure("binding_rejected")


def _ensure_unit_fits(messages: List[Dict[str, str]], unit_id: str) -> None:
    prompt_text = "\n".join(item.get("content") or "" for item in messages)
    if not fits_context(
        prompt_text,
        context_window=settings.LLM_CONTEXT_WINDOW_TOKENS,
        max_output_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
    ):
        raise ExtractFailure("context_exceeded", unit_id)


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
) -> Any:
    messages = build_extract_messages(
        schema=schema,
        target=target,
        source_text=unit["source"],
        unit_label=unit["label"],
    )
    _ensure_unit_fits(messages, unit["id"])

    repair_used = False
    requests_made = 0
    while requests_made < MAX_REQUESTS_PER_UNIT:
        if lost.is_set():
            raise ExtractFailure("claim_lost")

        consumed = await consume_extract_request(job_id, worker_id, attempts)
        if not consumed.get("allowed"):
            raise ExtractFailure(
                f"budget_{consumed.get('reason') or 'denied'}", unit["id"]
            )

        result: LLMResult = await invoke_llm(
            messages,
            json_mode=True,
            max_output_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
        )
        requests_made += 1
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

        kind = classify_finish(result.finish_reason)
        if kind == "truncated":
            raise ExtractFailure("response_truncated", unit["id"])
        if kind == "filtered":
            raise ExtractFailure("response_filtered", unit["id"])
        if kind == "unknown":
            if requests_made >= MAX_REQUESTS_PER_UNIT:
                raise ExtractFailure("completion_unknown", unit["id"])
            continue

        try:
            value = strict_json_loads(result.content)
        except StrictJSONError as exc:
            if repair_used or requests_made >= MAX_REQUESTS_PER_UNIT:
                raise ExtractFailure("invalid_json", f"{unit['id']}: {exc}") from exc
            messages = build_repair_messages(
                messages, result.content, [{"json_path": "$", "message": str(exc)}]
            )
            repair_used = True
            continue

        errors = validate_value(schema, value)
        if errors:
            if repair_used or requests_made >= MAX_REQUESTS_PER_UNIT:
                raise ExtractFailure("schema_validation_failed", f"{unit['id']}: {errors[0]}")
            messages = build_repair_messages(messages, result.content, errors)
            repair_used = True
            continue

        return value

    raise ExtractFailure("unit_failed", unit["id"])


async def _run_units(
    *,
    units: List[Dict[str, Any]],
    target: str,
    schema: Dict[str, Any],
    job_id: str,
    worker_id: str,
    attempts: int,
    lost: asyncio.Event,
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
            )
        )
    return outputs, calls


def _sum_tokens(calls: List[Dict[str, Any]], field: str) -> Optional[int]:
    values = [item.get(field) for item in calls]
    if not calls or any(not isinstance(value, int) for value in values):
        return None
    return sum(values)


def build_engine(spec: Dict[str, Any], calls: List[Dict[str, Any]], attempts: int) -> Dict[str, Any]:
    engine: Dict[str, Any] = {
        "name": "neoflow-extract",
        "target": spec["target"],
        "schema_hash": schema_hash(spec["data_schema"]),
        "schema_source": spec["schema_source"],
        "prompt_version": "v1",
        "attempts": attempts,
        "usage": {
            "requests": len(calls),
            "input_tokens": _sum_tokens(calls, "input_tokens"),
            "output_tokens": _sum_tokens(calls, "output_tokens"),
            "calls": calls[:ENGINE_MAX_CALLS],
        },
    }
    if len(json.dumps(engine, ensure_ascii=False)) > ENGINE_MAX_BYTES:
        engine["usage"].pop("calls", None)
    return engine


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
        logger.error(f"Extract Job 缺少认领信息: job_id={job_id}")
        if job_id:
            await update_job(job_id, "failed", error="extract_job_not_claimed")
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

        budget = await ensure_extract_budget(
            job_id,
            worker_id,
            attempts,
            settings.EXTRACT_MAX_REQUESTS_PER_JOB,
            settings.EXTRACT_TIMEOUT_SECONDS,
        )
        if budget.get("status") in ("not_found", "stale_token"):
            raise ExtractFailure(f"budget_{budget.get('status')}")

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
            )
            payload = assemble(spec["target"], outputs)
            final_errors = validate_output(spec["target"], spec["data_schema"], payload)
            if final_errors:
                raise ExtractFailure("final_validation_failed", str(final_errors[0]))
            engine = build_engine(spec, calls, attempts)
        finally:
            stop.set()
            if not heartbeat.done():
                await heartbeat
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

    status = await commit_extract_job(
        job_id,
        worker_id,
        attempts,
        "ok",
        extract_data=payload,
        engine=engine,
    )
    if status not in ("completed", "already_committed"):
        logger.warning(f"Extract 交卷未成功: job_id={job_id} status={status}")
        return None

    logger.info(
        f"Extract 完成: job_id={job_id} target={spec['target']} "
        f"schema_source={spec['schema_source']} requests={engine['usage']['requests']}"
    )
    return payload
