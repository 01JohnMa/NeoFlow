# api/jobs.py
"""内存 Job 管理器 - 用于跟踪异步处理任务状态"""

import time
import uuid
from typing import Dict, Any, Optional
from loguru import logger


# 阶段 → 进度百分比映射
STAGE_PROGRESS: Dict[str, int] = {
    "pending":   5,
    "ocr":       30,
    "llm":       70,
    "saving":    90,
    "completed": 100,
    "failed":    -1,
}

# Job TTL：1 小时后自动清理
_JOB_TTL_SECONDS = 3600

# 内存存储
_jobs: Dict[str, Dict[str, Any]] = {}


def create_job() -> str:
    """创建新 Job，返回 job_id"""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id":       job_id,
        "status":       "pending",   # pending | processing | completed | failed
        "stage":        "pending",   # pending | ocr | llm | saving | completed | failed
        "progress":     STAGE_PROGRESS["pending"],
        "document_ids": [],          # 完成后填入创建的文档 ID 列表
        "error":        None,
        "created_at":   time.monotonic(),
    }
    _cleanup_expired_jobs()
    return job_id


def update_job(job_id: str, stage: str, **extra: Any) -> None:
    """更新 Job 阶段和附加字段

    Args:
        job_id: Job ID
        stage: 新阶段（pending/ocr/llm/saving/completed/failed）
        **extra: 附加字段（如 document_ids、error）
    """
    if job_id not in _jobs:
        return

    if stage == "failed":
        status = "failed"
    elif stage == "completed":
        status = "completed"
    else:
        status = "processing"

    _jobs[job_id].update({
        "status":   status,
        "stage":    stage,
        "progress": STAGE_PROGRESS.get(stage, 5),
        **extra,
    })


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """按 ID 获取 Job，不存在返回 None"""
    return _jobs.get(job_id)


def _cleanup_expired_jobs() -> None:
    """清理超过 TTL 的旧 Job"""
    now = time.monotonic()
    expired = [
        jid for jid, job in _jobs.items()
        if now - job["created_at"] > _JOB_TTL_SECONDS
    ]
    for jid in expired:
        _jobs.pop(jid, None)
    if expired:
        logger.debug(f"清理过期任务: {len(expired)} 个")
