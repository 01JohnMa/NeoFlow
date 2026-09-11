"""文档处理 worker 测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import DOCUMENT_ID, TENANT_ID, TEMPLATE_ID, USER_ID


@pytest.mark.asyncio
async def test_execute_single_job_uses_persisted_document_metadata():
    """single/template job 应由 worker 根据文档记录执行，而不是 API 进程执行。"""
    from workers.document_worker import execute_job

    job = {
        "job_id": "job-single",
        "job_type": "template",
        "document_ids": [DOCUMENT_ID],
        "created_by": USER_ID,
    }
    document = {
        "id": DOCUMENT_ID,
        "file_path": "/tmp/test.pdf",
        "template_id": TEMPLATE_ID,
        "tenant_id": TENANT_ID,
        "custom_push_name": "推送名",
    }

    with patch("workers.document_worker.supabase_service") as mock_supabase, \
         patch("workers.document_worker.process_document_task", new_callable=AsyncMock) as mock_task:
        mock_supabase.get_document = AsyncMock(return_value=document)

        await execute_job(job)

    mock_task.assert_awaited_once_with(
        document_id=DOCUMENT_ID,
        file_path="/tmp/test.pdf",
        template_id=TEMPLATE_ID,
        tenant_id=TENANT_ID,
        custom_push_name="推送名",
        job_id="job-single",
    )


@pytest.mark.asyncio
async def test_execute_crm_job_waits_for_crm_review():
    """CRM job 只负责提取入库，不应自动通过或自动推飞书。"""
    from workers.document_worker import execute_job

    job = {
        "job_id": "job-crm",
        "job_type": "crm",
        "document_ids": [DOCUMENT_ID],
        "created_by": USER_ID,
    }
    document = {
        "id": DOCUMENT_ID,
        "file_path": "/tmp/test.pdf",
        "template_id": TEMPLATE_ID,
        "tenant_id": TENANT_ID,
        "custom_push_name": "CRM推送名",
    }

    with patch("workers.document_worker.supabase_service") as mock_supabase, \
         patch("workers.document_worker.process_document_task", new_callable=AsyncMock) as mock_task:
        mock_supabase.get_document = AsyncMock(return_value=document)

        await execute_job(job)

    mock_task.assert_awaited_once_with(
        document_id=DOCUMENT_ID,
        file_path="/tmp/test.pdf",
        template_id=TEMPLATE_ID,
        tenant_id=TENANT_ID,
        custom_push_name="CRM推送名",
        job_id="job-crm",
        force_pending_review=True,
    )


@pytest.mark.asyncio
async def test_poll_once_claims_and_executes_one_job():
    """worker 单轮轮询应认领一个 job 并执行它。"""
    from workers.document_worker import poll_once

    job = {"job_id": "job-single", "job_type": "template", "document_ids": [DOCUMENT_ID]}

    with patch("workers.document_worker.claim_next_job", new_callable=AsyncMock, return_value=job) as mock_claim, \
         patch("workers.document_worker.execute_job", new_callable=AsyncMock) as mock_execute:
        did_work = await poll_once("worker-1")

    assert did_work is True
    mock_claim.assert_awaited_once()
    assert mock_claim.await_args.args[0] == "worker-1"
    mock_execute.assert_awaited_once_with(job)
