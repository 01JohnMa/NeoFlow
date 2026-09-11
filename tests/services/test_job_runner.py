# tests/services/test_job_runner.py
"""JobRunner seam 测试 — 按 Configuration Type 分发、Revision 固定、legacy 兼容。"""

from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import DOCUMENT_ID, TEMPLATE_ID, TENANT_ID

REVISION_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
CONFIG_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


def _job(**overrides):
    job = {
        "job_id": "job-1",
        "job_type": "batch",
        "document_ids": [DOCUMENT_ID],
        "configuration_revision_id": REVISION_ID,
        "tenant_id": TENANT_ID,
    }
    job.update(overrides)
    return job


class TestDispatch:
    @pytest.mark.asyncio
    async def test_dispatches_by_configuration_type_and_pins_revision(self):
        from services.job_runner import JobRunner

        seen = {}

        async def fake_handler(*, job, revision, configuration):
            seen.update(job=job, revision=revision, configuration=configuration)
            return "ok"

        runner = JobRunner(handlers={
            "extract": fake_handler,
            "parse": AsyncMock(side_effect=AssertionError("不应分发到 parse")),
        })
        revision = {"id": REVISION_ID, "configuration_id": CONFIG_ID, "revision_number": 3}
        configuration = {"id": CONFIG_ID, "type": "extract", "status": "published"}

        with patch("services.job_runner.configuration_service") as mock_svc:
            mock_svc.get_revision = AsyncMock(return_value=revision)
            mock_svc.get_configuration = AsyncMock(return_value=configuration)
            result = await runner.run(_job())

        assert result == "ok"
        mock_svc.get_revision.assert_awaited_once_with(REVISION_ID)
        mock_svc.get_configuration.assert_awaited_once_with(CONFIG_ID)
        assert seen["revision"] == revision
        assert seen["configuration"] == configuration
        assert seen["job"]["configuration_revision_id"] == REVISION_ID

    @pytest.mark.asyncio
    async def test_unknown_handler_rejected(self):
        from services.job_runner import JobRunner, JobRunnerError

        runner = JobRunner(handlers={})
        revision = {"id": REVISION_ID, "configuration_id": CONFIG_ID}
        configuration = {"id": CONFIG_ID, "type": "parse", "status": "published"}

        with patch("services.job_runner.configuration_service") as mock_svc:
            mock_svc.get_revision = AsyncMock(return_value=revision)
            mock_svc.get_configuration = AsyncMock(return_value=configuration)
            with pytest.raises(JobRunnerError):
                await runner.run(_job())

    @pytest.mark.asyncio
    async def test_missing_revision_rejected(self):
        from services.job_runner import JobRunner, JobRunnerError

        runner = JobRunner(handlers={"extract": AsyncMock()})
        with patch("services.job_runner.configuration_service") as mock_svc:
            mock_svc.get_revision = AsyncMock(return_value=None)
            with pytest.raises(JobRunnerError):
                await runner.run(_job())

    @pytest.mark.asyncio
    async def test_legacy_job_without_revision_uses_extract_handler(self):
        from services.job_runner import JobRunner

        handler = AsyncMock(return_value="legacy-ok")
        runner = JobRunner(handlers={"extract": handler})

        with patch("services.job_runner.configuration_service") as mock_svc:
            result = await runner.run(_job(configuration_revision_id=None))

        assert result == "legacy-ok"
        mock_svc.get_revision.assert_not_called()
        assert handler.await_args.kwargs["revision"] is None
        assert handler.await_args.kwargs["configuration"] is None


class TestDefaultHandlers:
    def test_default_runner_registers_extract_and_parse(self):
        from services.job_runner import (
            EXTRACT_CONFIGURATION_TYPE,
            PARSE_CONFIGURATION_TYPE,
            JobRunner,
        )

        handlers = JobRunner().handlers
        assert EXTRACT_CONFIGURATION_TYPE in handlers
        assert PARSE_CONFIGURATION_TYPE in handlers

    @pytest.mark.asyncio
    async def test_default_runner_dispatches_parse_jobs(self):
        from services.job_runner import JobRunner

        revision = {"id": REVISION_ID, "configuration_id": CONFIG_ID}
        configuration = {"id": CONFIG_ID, "type": "parse", "status": "published"}

        with patch("services.parse_service.handle_parse_job", new_callable=AsyncMock) as mock_handler, \
             patch("services.job_runner.configuration_service") as mock_svc:
            mock_handler.return_value = "parse-ok"
            mock_svc.get_revision = AsyncMock(return_value=revision)
            mock_svc.get_configuration = AsyncMock(return_value=configuration)

            result = await JobRunner().run(_job())

        assert result == "parse-ok"
        assert mock_handler.await_args.kwargs["configuration"]["type"] == "parse"


class TestExtractHandler:
    @pytest.mark.asyncio
    async def test_builds_legacy_task_kwargs_with_pinned_revision(self):
        from services.job_runner import handle_extract_job

        document = {
            "id": DOCUMENT_ID,
            "file_path": "/tmp/test.pdf",
            "template_id": TEMPLATE_ID,
            "tenant_id": TENANT_ID,
            "custom_push_name": "推送名",
        }

        with patch("services.supabase_service.supabase_service") as mock_supabase, \
             patch("api.routes.documents.process.process_document_task", new_callable=AsyncMock) as mock_task, \
             patch("api.jobs.update_job", new_callable=AsyncMock):
            mock_supabase.get_document = AsyncMock(return_value=document)

            await handle_extract_job(
                job=_job(),
                revision={"id": REVISION_ID},
                configuration={"type": "extract"},
            )

        mock_task.assert_awaited_once_with(
            document_id=DOCUMENT_ID,
            file_path="/tmp/test.pdf",
            template_id=TEMPLATE_ID,
            tenant_id=TENANT_ID,
            custom_push_name="推送名",
            job_id="job-1",
            configuration_revision_id=REVISION_ID,
        )

    @pytest.mark.asyncio
    async def test_crm_job_waits_for_crm_review(self):
        from services.job_runner import handle_extract_job

        document = {
            "id": DOCUMENT_ID,
            "file_path": "/tmp/test.pdf",
            "template_id": TEMPLATE_ID,
            "tenant_id": TENANT_ID,
            "custom_push_name": "CRM推送名",
        }

        with patch("services.supabase_service.supabase_service") as mock_supabase, \
             patch("api.routes.documents.process.process_document_task", new_callable=AsyncMock) as mock_task, \
             patch("api.jobs.update_job", new_callable=AsyncMock):
            mock_supabase.get_document = AsyncMock(return_value=document)

            await handle_extract_job(job=_job(job_type="crm"))

        assert mock_task.await_args.kwargs["force_pending_review"] is True

    @pytest.mark.asyncio
    async def test_missing_document_marks_job_failed(self):
        from services.job_runner import handle_extract_job

        with patch("services.supabase_service.supabase_service") as mock_supabase, \
             patch("api.routes.documents.process.process_document_task", new_callable=AsyncMock) as mock_task, \
             patch("api.jobs.update_job", new_callable=AsyncMock) as mock_update:
            mock_supabase.get_document = AsyncMock(return_value=None)

            result = await handle_extract_job(job=_job())

        assert result is None
        mock_update.assert_awaited_once()
        assert mock_update.await_args.args[1] == "failed"
        mock_task.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_document_ids_marks_job_failed(self):
        from services.job_runner import handle_extract_job

        with patch("services.supabase_service.supabase_service") as mock_supabase, \
             patch("api.routes.documents.process.process_document_task", new_callable=AsyncMock) as mock_task, \
             patch("api.jobs.update_job", new_callable=AsyncMock) as mock_update:
            result = await handle_extract_job(job=_job(document_ids=[]))

        assert result is None
        mock_update.assert_awaited_once()
        mock_supabase.get_document.assert_not_called()
        mock_task.assert_not_awaited()
