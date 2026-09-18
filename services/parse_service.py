# services/parse_service.py
"""Parse Job handler：解析文档并落 Result（参数化执行规格，ADR-0007）。

- execution_spec：单文件、冻结参数、心跳续租、commit_parse_job 原子交卷
"""

import asyncio
from typing import Any, Dict, Optional

from loguru import logger

from config.settings import settings
from services.configuration_service import PARSE_DEFAULTS
from services.parse_postprocess import detect_repeated_texts, strip_watermark_content
from services.parse_result import ParseResult
from services.parser_adapter import get_parser_adapter
from services.result_service import result_service


SUPPORTED_PARSE_MODES = ("pipeline", "vlm")


def normalize_parse_mode(mode: Optional[str]) -> str:
    """解析模式只支持 pipeline / vlm，非法值回退快速解析。"""
    return mode if mode in SUPPORTED_PARSE_MODES else "pipeline"


def apply_parse_postprocess(result: ParseResult, params: Dict[str, Any]) -> None:
    """按冻结参数执行解析产物后处理（当前仅水印过滤）。

    - 指定了关键词：按关键词过滤；
    - 未指定：自动识别全文重复出现的文本（阈值由策略配置）。
    """
    if not params.get("remove_watermark"):
        return
    keywords = params.get("watermark_keywords") or []
    if keywords:
        removed = strip_watermark_content(result, keywords=keywords)
    else:
        auto_texts = detect_repeated_texts(result, settings.PARSE_WATERMARK_REPEAT_THRESHOLD)
        removed = strip_watermark_content(result, auto_texts=auto_texts)
    if removed:
        logger.info(f"水印过滤移除 {removed} 个块: engine={result.engine.get('name')}")


def build_parse_params(
    configuration: Optional[Dict[str, Any]] = None,
    revision: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """合并 parse 参数默认值与 Revision definition.parse（Revision 优先）。"""
    definition: Dict[str, Any] = {}
    if revision:
        definition = revision.get("definition") or {}
    elif configuration:
        definition = configuration.get("draft_definition") or {}

    params: Dict[str, Any] = dict(PARSE_DEFAULTS)
    section = definition.get("parse")
    if isinstance(section, dict):
        params.update(section)
    return params


async def ensure_parse_result(
    *,
    document_id: str,
    file_path: str,
    tenant_id: Optional[str],
    job_id: Optional[str] = None,
    parse_section: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """返回文档最新 ParseResult 的 data；缺失时按需自动解析一次。

    - 已有 ParseResult：直接返回其 data
    - 无 ParseResult 且配置了 MINERU_API_KEY：调用 ParserAdapter 解析并落 Result
      （解析参数取自配置的 parse 段，缺省用 PARSE_DEFAULTS）
    - 无 key 或解析失败：返回 None（调用方按失败处理）
    """
    existing = await result_service.get_document_parse_result(
        document_id,
        tenant_id=tenant_id,
    )
    if existing and existing.get("data"):
        return existing["data"]

    if not settings.MINERU_API_KEY:
        logger.warning(
            f"无 ParseResult 且未配置 MINERU_API_KEY，无法解析: {document_id}"
        )
        return None

    params = build_parse_params(
        configuration={"draft_definition": {"parse": parse_section or {}}}
    )
    try:
        adapter = get_parser_adapter(params)
        result = await adapter.parse(file_path, params)
    except Exception as exc:
        logger.warning(f"自动解析失败: document_id={document_id}, error={exc}")
        return None

    parse_data = result.to_dict()
    stored = await result_service.record_parse_result(
        tenant_id=tenant_id,
        document_id=document_id,
        parse_data=parse_data,
        job_id=job_id,
    )
    if not stored:
        return None
    return parse_data


async def _heartbeat_until(
    stop_event: "asyncio.Event",
    *,
    job_id: str,
    worker_id: str,
    attempts: int,
    interval: float,
) -> None:
    """长任务心跳：定时续租，认领失效即退出。"""
    from api.jobs import renew_job_claim

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            return
        except asyncio.TimeoutError:
            pass
        if not await renew_job_claim(job_id, worker_id, attempts):
            logger.warning(f"Parse 心跳续租失败，认领已失效: job_id={job_id}")
            return


async def _commit_parameterized_job(
    job_id: str,
    worker_id: str,
    attempts: int,
    outcome: str,
    error: Optional[str] = None,
    parse_data: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """参数化 Parse 的交卷（原子 RPC）。"""
    from api.jobs import commit_parse_job

    status = await commit_parse_job(
        job_id, worker_id, attempts, outcome, error=error, parse_data=parse_data
    )
    if status not in ("completed", "failed", "already_committed"):
        logger.warning(f"Parse 交卷未确认: job_id={job_id}, status={status}")
    return status


async def _handle_parameterized_parse_job(
    job: Dict[str, Any],
    spec: Dict[str, Any],
) -> Any:
    """参数化 Parse（execution_spec）：单文件、冻结参数、认领感知写入。"""
    from api.jobs import update_job, update_job_if_owned
    from services.parse_request_service import PARSE_CAPABILITY, PARSE_SPEC_VERSION
    from services.supabase_service import supabase_service

    job_id = str(job.get("job_id"))
    worker_id = job.get("locked_by")
    attempts = job.get("attempts")

    if not worker_id or attempts is None:
        await update_job(job_id, "failed", error="参数化 Parse Job 缺少认领令牌")
        return None

    if spec.get("capability") != PARSE_CAPABILITY:
        await _commit_parameterized_job(
            job_id, worker_id, attempts, "failed",
            f"不支持的执行能力: {spec.get('capability')}",
        )
        return None
    if spec.get("spec_version") != PARSE_SPEC_VERSION:
        await _commit_parameterized_job(
            job_id, worker_id, attempts, "failed",
            f"不支持的执行规格版本: {spec.get('spec_version')}",
        )
        return None

    document_ids = job.get("document_ids") or []
    if len(document_ids) != 1:
        await _commit_parameterized_job(
            job_id, worker_id, attempts, "failed",
            "参数化 Parse Job 必须且只能包含一个文档",
        )
        return None

    document_id = str(document_ids[0])
    document = await supabase_service.get_document(document_id)
    if not document or not document.get("file_path"):
        await _commit_parameterized_job(
            job_id, worker_id, attempts, "failed", f"文档不存在或缺少文件: {document_id}"
        )
        return None

    params = dict(spec.get("effective_params") or {})

    if not await update_job_if_owned(job_id, worker_id, attempts, "parsing"):
        logger.warning(f"Parse 任务认领已失效，跳过执行: job_id={job_id}")
        return None

    stop_event = asyncio.Event()
    interval = max(30.0, float(settings.DOC_WORKER_STALE_LOCK_SECONDS) / 3.0)
    heartbeat = asyncio.create_task(
        _heartbeat_until(
            stop_event,
            job_id=job_id,
            worker_id=worker_id,
            attempts=attempts,
            interval=interval,
        )
    )

    try:
        adapter = get_parser_adapter(params)
        result = await adapter.parse(document["file_path"], params)
    except Exception as exc:
        logger.opt(exception=exc).error(
            f"参数化 Parse 失败: job_id={job_id}, document_id={document_id}"
        )
        stop_event.set()
        await heartbeat
        await _commit_parameterized_job(
            job_id, worker_id, attempts, "failed", str(exc)
        )
        return None
    finally:
        stop_event.set()
        if not heartbeat.done():
            await heartbeat

    apply_parse_postprocess(result, params)

    if not await update_job_if_owned(job_id, worker_id, attempts, "saving"):
        # 解析期间认领失效：不得提交产物
        return None

    await _commit_parameterized_job(
        job_id, worker_id, attempts, "ok", parse_data=result.to_dict()
    )
    return result


async def handle_parse_job(
    job: Dict[str, Any],
    revision: Optional[Dict[str, Any]] = None,
    configuration: Optional[Dict[str, Any]] = None,
) -> Any:
    """JobRunner 的 parse handler（仅参数化路径，ADR-0007）。"""
    spec = job.get("execution_spec")
    if isinstance(spec, dict) and spec:
        return await _handle_parameterized_parse_job(job, spec)

    from api.jobs import update_job

    job_id = str(job.get("job_id"))
    await update_job(job_id, "failed", error="Parse Job 缺少执行规格（execution_spec）")
    return None
