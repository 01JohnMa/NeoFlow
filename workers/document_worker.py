"""文档处理独立 worker。

API 进程只负责创建 processing_jobs；本模块负责认领并执行重 OCR/VLM/LLM 任务。
"""

import asyncio
import os
import socket
from typing import Any, Dict

from loguru import logger

from api.jobs import claim_next_job, update_job
from config.settings import settings
from services.job_runner import job_runner
from services.ocr_service import ocr_service
from services.supabase_service import supabase_service


def build_worker_id() -> str:
    """构建稳定可读的 worker id。"""
    if settings.DOC_WORKER_ID:
        return settings.DOC_WORKER_ID
    return f"{socket.gethostname()}:{os.getpid()}"


async def execute_job(job: Dict[str, Any]) -> None:
    """执行一个已认领 job（统一走 JobRunner seam，按 Configuration Type 分发）。"""
    await job_runner.run(job)


async def poll_once(worker_id: str) -> bool:
    """认领并执行一个 job。返回本轮是否执行了任务。"""
    job = await claim_next_job(worker_id, settings.DOC_WORKER_STALE_LOCK_SECONDS)
    if not job:
        return False

    logger.info(f"[worker={worker_id}] 认领任务: {job.get('job_id')} type={job.get('job_type')}")
    try:
        await execute_job(job)
    except Exception as exc:
        logger.opt(exception=exc).error(f"[worker={worker_id}] 任务执行异常: {job.get('job_id')}")
        await update_job(str(job.get("job_id")), "failed", error=str(exc))
    return True


async def run_forever(worker_id: Optional[str] = None) -> None:
    """持续轮询并执行任务。"""
    effective_worker_id = worker_id or build_worker_id()
    logger.info(f"文档 worker 启动: {effective_worker_id}")

    try:
        await supabase_service.initialize()
    except Exception as exc:
        logger.opt(exception=exc).warning("Supabase 初始化失败，worker 将在任务执行时继续尝试")

    if settings.OCR_ENABLED:
        try:
            await ocr_service.initialize()
        except Exception as exc:
            logger.opt(exception=exc).warning("OCR 初始化失败，worker 将在任务执行时继续尝试")

    while True:
        did_work = await poll_once(effective_worker_id)
        if not did_work:
            await asyncio.sleep(settings.DOC_WORKER_POLL_INTERVAL_SECONDS)


def main() -> None:
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
