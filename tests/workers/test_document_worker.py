"""文档处理 worker 测试。"""

import asyncio
from unittest.mock import AsyncMock, patch

import httpx

import pytest

from tests.conftest import DOCUMENT_ID


@pytest.mark.asyncio
async def test_execute_job_delegates_to_job_runner():
    """worker 领取后统一交给 JobRunner seam 分发执行。"""
    from workers.document_worker import execute_job

    job = {
        "job_id": "job-single",
        "document_ids": [DOCUMENT_ID],
        "execution_spec": {"capability": "parse", "spec_version": "1"},
    }

    with patch("workers.document_worker.job_runner") as mock_runner:
        mock_runner.run = AsyncMock()

        await execute_job(job)

    mock_runner.run.assert_awaited_once_with(job)


@pytest.mark.asyncio
async def test_poll_once_claims_and_executes_one_job():
    """worker 单轮轮询应认领一个 job 并执行它。"""
    from workers.document_worker import poll_once

    job = {"job_id": "job-single", "document_ids": [DOCUMENT_ID]}

    with patch("workers.document_worker.claim_next_job", new_callable=AsyncMock, return_value=job) as mock_claim, \
         patch("workers.document_worker.execute_job", new_callable=AsyncMock) as mock_execute:
        did_work = await poll_once("worker-1")

    assert did_work is True
    mock_claim.assert_awaited_once()
    assert mock_claim.await_args.args[0] == "worker-1"
    mock_execute.assert_awaited_once_with(job)


@pytest.mark.asyncio
async def test_worker_recovers_from_queue_transport_failure():
    """A broken queue connection must not stop the worker; cancellation still stops it."""
    from workers import document_worker

    job = {"job_id": "queued-after-disconnect", "document_ids": [DOCUMENT_ID]}
    with patch.object(document_worker.supabase_service, "initialize", new_callable=AsyncMock), \
         patch.object(document_worker, "claim_next_job", new_callable=AsyncMock,
                      side_effect=[httpx.WriteError("Broken pipe"), job, asyncio.CancelledError()]) as claim, \
         patch.object(document_worker, "execute_job", new_callable=AsyncMock) as execute, \
         patch.object(document_worker.asyncio, "sleep", new_callable=AsyncMock) as sleep:
        with pytest.raises(asyncio.CancelledError):
            await document_worker.run_forever("worker-recovery-test")

    assert claim.await_count == 3
    execute.assert_awaited_once_with(job)
    sleep.assert_awaited_once()
