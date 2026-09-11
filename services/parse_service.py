# services/parse_service.py
"""Parse Job handler：按固定 Revision 的 parse 参数解析文档并落 Result。

执行入口仍是 JobRunner seam；本模块只做三件事：
1. 从 Revision definition 的 parse 段落取解析参数（缺省用 PARSE_DEFAULTS）；
2. 通过 ParserAdapter 产出 ParseResult；
3. 整体 JSONB 写入 results 表（sample_key=parse），并推进 Job 状态。
"""

from typing import Any, Dict, Optional

from loguru import logger

from services.configuration_service import PARSE_DEFAULTS
from services.parser_adapter import get_parser_adapter
from services.result_service import result_service


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


async def handle_parse_job(
    job: Dict[str, Any],
    revision: Optional[Dict[str, Any]] = None,
    configuration: Optional[Dict[str, Any]] = None,
) -> Any:
    """JobRunner 的 parse handler。"""
    from api.jobs import update_job
    from services.supabase_service import supabase_service

    job_id = str(job.get("job_id"))
    document_ids = job.get("document_ids") or []
    if not document_ids:
        await update_job(job_id, "failed", error="任务缺少 document_ids")
        return None

    document_id = document_ids[0]
    document = await supabase_service.get_document(document_id)
    if not document:
        await update_job(job_id, "failed", error=f"文档不存在: {document_id}")
        return None

    file_path = document.get("file_path") or ""
    if not file_path:
        await update_job(job_id, "failed", error="文档缺少 file_path")
        return None

    params = build_parse_params(configuration, revision)
    await update_job(job_id, "ocr")

    adapter = get_parser_adapter(params)
    try:
        result = await adapter.parse(file_path, params)
    except Exception as exc:
        logger.opt(exception=exc).error(f"Parse job 失败: job_id={job_id}")
        await update_job(job_id, "failed", error=str(exc))
        return None

    await update_job(job_id, "saving")
    stored = await result_service.record_parse_result(
        tenant_id=document.get("tenant_id") or job.get("tenant_id"),
        document_id=document_id,
        parse_data=result.to_dict(),
        job_id=job_id,
        config_revision_id=job.get("configuration_revision_id"),
    )
    if not stored:
        await update_job(job_id, "failed", error="ParseResult 写入失败")
        return None

    await update_job(job_id, "completed")
    return result
