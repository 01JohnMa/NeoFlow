# api/jobs.py
"""持久化 Job 管理器 - 用于跟踪异步处理任务状态与防重记录"""

import hashlib
import inspect
import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from loguru import logger

from services.supabase_service import supabase_service


# 阶段 → 进度百分比映射
STAGE_PROGRESS: Dict[str, int] = {
    "queued": 0,
    "pending": 5,
    "ocr": 30,
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


async def create_job(
    *,
    job_type: str = "batch",
    created_by: Optional[str] = None,
    related_document_ids: Optional[list[str]] = None,
) -> str:
    """创建持久化 Job，返回 job_id。"""
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
