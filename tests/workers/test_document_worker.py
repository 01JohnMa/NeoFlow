"""文档处理 worker 测试。"""

from unittest.mock import AsyncMock, patch

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
