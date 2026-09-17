# api/jobs.py
"""持久化 Job 管理器 - 用于跟踪异步处理任务状态与防重记录"""

import hashlib
import inspect
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from services.supabase_service import supabase_service


# 阶段 → 进度百分比映射
STAGE_PROGRESS: Dict[str, int] = {
    "queued": 0,
    "pending": 5,
    "parsing": 30,
    "llm": 70,
    "saving": 90,
    "completed": 100,
    "failed": -1,
}


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat()


def _job_table():
    return supabase_service.client.table("processing_jobs")


def _push_record_table():
    return supabase_service.client.table("feishu_push_records")


async def _run_db(fn):
    runner = getattr(supabase_service, "_run_sync", None)
    if runner is not None and inspect.iscoroutinefunction(runner):
        return await runner(fn)
    return fn()


def _normalize_job_record(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    normalized = dict(row)
    normalized.setdefault("job_id", normalized.get("id"))
    normalized.setdefault("status", "queued")
    normalized.setdefault("stage", "queued")
    normalized.setdefault("progress", STAGE_PROGRESS.get(normalized["stage"], 0))
    normalized.setdefault("document_ids", [])
    normalized.setdefault("error", None)
    return normalized


async def list_jobs(
    *,
    tenant_id: Optional[str] = None,
    document_id: Optional[str] = None,
    configuration_revision_id: Optional[str] = None,
    created_by: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """按租户/文档/Revision/发起人查询 Job（新→旧），供列表接口使用。"""

    def _query():
        query = _job_table().select("*").order("created_at", desc=True).limit(limit)
        if tenant_id:
            query = query.eq("tenant_id", tenant_id)
        if configuration_revision_id:
            query = query.eq("configuration_revision_id", configuration_revision_id)
        if document_id:
            query = query.contains("document_ids", [document_id])
        if created_by:
            query = query.eq("created_by", created_by)
        return query.execute()

    result = await _run_db(_query)
    jobs: List[Dict[str, Any]] = []
    for row in result.data or []:
        normalized = _normalize_job_record(row)
        if normalized:
            jobs.append(normalized)
    return jobs


async def create_job(
    *,
    job_type: str = "batch",
    created_by: Optional[str] = None,
    related_document_ids: Optional[list[str]] = None,
    tenant_id: Optional[str] = None,
    configuration_revision_id: Optional[str] = None,
) -> str:
    """创建持久化 Job，返回 job_id。

    configuration_revision_id 用于固定创建时选定的 Configuration Revision；
    历史调用不传时为 NULL，worker 仍按旧文档处理流程执行。
    """
    job_id = str(uuid.uuid4())
    payload: Dict[str, Any] = {
        "job_id": job_id,
        "job_type": job_type,
        "status": "queued",
        "stage": "queued",
        "progress": STAGE_PROGRESS["queued"],
        "document_ids": related_document_ids or [],
        "error": None,
        "created_by": created_by,
        "tenant_id": tenant_id,
        "configuration_revision_id": configuration_revision_id,
        "created_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
    }
    result = await _run_db(
        lambda: _job_table().insert(payload).execute()
    )
    created = (result.data or [{}])[0]
    return created.get("job_id") or job_id


async def update_job(job_id: str, stage: str, **extra: Any) -> None:
    """更新 Job 阶段和附加字段。"""
    if stage == "failed":
        status = "failed"
    elif stage == "completed":
        status = "completed"
    elif stage in ("queued", "pending"):
        status = "queued"
    else:
        status = "processing"

    payload = {
        "status": status,
        "stage": stage,
        "progress": STAGE_PROGRESS.get(stage, 0),
        "updated_at": _utc_now_iso(),
        **extra,
    }
    if status in ("completed", "failed"):
        payload.setdefault("finished_at", _utc_now_iso())
        payload.setdefault("locked_by", None)
        payload.setdefault("locked_at", None)
    await _run_db(
        lambda: _job_table().update(payload).eq("job_id", job_id).execute()
    )


async def update_job_if_owned(
    job_id: str,
    worker_id: str,
    attempts: int,
    stage: str,
    **extra: Any,
) -> bool:
    """认领感知更新：仅当仍持有认领令牌（worker + attempt + processing）时生效。

    返回是否真正更新到行；False 表示认领已失效，调用方应停止写入。
    """
    payload = {
        "stage": stage,
        "progress": STAGE_PROGRESS.get(stage, 0),
        "updated_at": _utc_now_iso(),
        **extra,
    }
    result = await _run_db(
        lambda: _job_table().update(payload)
        .eq("job_id", job_id)
        .eq("locked_by", worker_id)
        .eq("attempts", attempts)
        .eq("status", "processing")
        .execute()
    )
    return bool(result.data)


async def renew_job_claim(job_id: str, worker_id: str, attempts: int) -> bool:
    """心跳续租：仅持有认领时刷新 locked_at，避免长任务被重领。"""
    result = await _run_db(
        lambda: _job_table().update({
            "locked_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        })
        .eq("job_id", job_id)
        .eq("locked_by", worker_id)
        .eq("attempts", attempts)
        .eq("status", "processing")
        .execute()
    )
    return bool(result.data)


async def commit_parse_job(
    job_id: str,
    worker_id: str,
    attempts: int,
    outcome: str,
    error: Optional[str] = None,
    parse_data: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """原子交卷（迁移 024 RPC）：锁 Job、校验认领、写规范产物或失败终态。

    返回 completed / failed / already_committed / stale_token / stale / not_found。
    """
    result = await _run_db(
        lambda: supabase_service.client.rpc(
            "commit_parse_job",
            {
                "p_job_id": job_id,
                "p_worker_id": worker_id,
                "p_attempts": attempts,
                "p_outcome": outcome,
                "p_error": error,
                "p_parse_data": parse_data,
            },
        ).execute()
    )
    data = result.data or []
    row = data if isinstance(data, dict) else (data[0] if data else None)
    return (row or {}).get("out_status")


async def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """按 ID 获取 Job，不存在返回 None。"""
    result = await _run_db(
        lambda: _job_table().select("*").eq("job_id", job_id).limit(1).execute()
    )
    row = result.data[0] if result.data else None
    return _normalize_job_record(row)


async def claim_next_job(worker_id: str, stale_after_seconds: int = 1800) -> Optional[Dict[str, Any]]:
    """原子认领下一个 queued job。没有可执行任务时返回 None。"""
    result = await _run_db(
        lambda: supabase_service.client.rpc(
            "claim_next_processing_job",
            {
                "p_worker_id": worker_id,
                "p_stale_after_seconds": stale_after_seconds,
            },
        ).execute()
    )
    data = result.data or []
    if isinstance(data, dict):
        row = data
    else:
        row = data[0] if data else None
    return _normalize_job_record(row)


async def has_feishu_push_record(dedupe_key: str) -> bool:
    """检查飞书推送是否已记录。"""
    result = await _run_db(
        lambda: _push_record_table().select("dedupe_key").eq("dedupe_key", dedupe_key).limit(1).execute()
    )
    return bool(result.data)


async def record_feishu_push(dedupe_key: str, document_id: str, template_id: Optional[str] = None) -> None:
    """记录飞书推送成功，供幂等防重使用。"""
    payload = {
        "dedupe_key": dedupe_key,
        "document_id": document_id,
        "template_id": template_id,
        "created_at": _utc_now_iso(),
    }
    await _run_db(
        lambda: _push_record_table().insert(payload).execute()
    )


def build_feishu_push_dedupe_key(document_id: str, template_id: Optional[str], extraction_data: dict) -> str:
    """构建飞书推送去重键。"""
    serialized = json.dumps(extraction_data or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    return f"feishu:{document_id}:{template_id or 'none'}:{digest}"
