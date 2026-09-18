# tests/services/test_job_runner.py
"""JobRunner seam 测试 — 按 Configuration Type 分发、Revision 固定、legacy 兼容。"""

from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import DOCUMENT_ID, TENANT_ID

REVISION_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
CONFIG_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


def _job(**overrides):
    job = {
        "job_id": "job-1",
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
    async def test_job_without_execution_definition_rejected(self):
        """无 execution_spec 且无 Revision：来源不明，fail-closed 不回落旧抽取。"""
        from services.job_runner import JobRunner, JobRunnerError

        handler = AsyncMock()
        runner = JobRunner(handlers={"extract": handler})

        with patch("services.job_runner.configuration_service") as mock_svc:
            with pytest.raises(JobRunnerError):
                await runner.run(_job(configuration_revision_id=None))

        mock_svc.get_revision.assert_not_called()
        handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_execution_spec_dispatches_capability_without_revision(self):
        from services.job_runner import JobRunner

        handler = AsyncMock(return_value="parse-ok")
        runner = JobRunner(handlers={"parse": handler})
        job = _job(
            configuration_revision_id=None,
            execution_spec={
                "capability": "parse",
                "spec_version": "1",
                "effective_params": {"model_version": "vlm"},
            },
        )

        with patch("services.job_runner.configuration_service") as mock_svc:
            result = await runner.run(job)

        assert result == "parse-ok"
        mock_svc.get_revision.assert_not_called()
        assert handler.await_args.kwargs["revision"] is None
        assert handler.await_args.kwargs["configuration"] is None

    @pytest.mark.asyncio
    async def test_execution_spec_without_capability_rejected(self):
        from services.job_runner import JobRunner, JobRunnerError

        runner = JobRunner(handlers={"parse": AsyncMock()})
        with pytest.raises(JobRunnerError):
            await runner.run(_job(configuration_revision_id=None, execution_spec={"spec_version": "1"}))


class TestDefaultHandlers:
    def test_default_runner_registers_extract_and_parse(self):
        from services.job_runner import (
            CLASSIFY_CONFIGURATION_TYPE,
            EXTRACT_CONFIGURATION_TYPE,
            PARSE_CONFIGURATION_TYPE,
            SPLIT_CONFIGURATION_TYPE,
            JobRunner,
        )

        handlers = JobRunner().handlers
        assert EXTRACT_CONFIGURATION_TYPE in handlers
        assert PARSE_CONFIGURATION_TYPE in handlers
        assert CLASSIFY_CONFIGURATION_TYPE in handlers
        assert SPLIT_CONFIGURATION_TYPE in handlers

    @pytest.mark.asyncio
    async def test_classify_handler_consumes_parse_result_and_persists_result(self):
        from services.job_runner import handle_classify_job

        parse_row = {"id": "parse-1", "data": {"markdown": "invoice", "pages": []}}
        stored = {"id": "result-1"}
        with patch("agents.workflow.document_workflow") as mock_workflow, \
             patch("services.result_service.result_service") as mock_result, \
             patch("api.jobs.update_job", new_callable=AsyncMock) as mock_update, \
             patch("services.classify_split_service.run_classify", new_callable=AsyncMock) as mock_run:
            mock_workflow._llm_invoke_with_retry = AsyncMock()
            mock_result.get_document_parse_result = AsyncMock(return_value=parse_row)
            mock_result.build_result_row.return_value = {"data": {"label": "invoice"}}
            mock_result.create_result = AsyncMock(return_value=stored)
            mock_run.return_value = {"label": "invoice", "confidence": 0.9, "source_refs": []}

            result = await handle_classify_job(
                job=_job(),
                revision={"definition": {"classify": {"rules": ["invoice"]}}},
                configuration={"type": "classify"},
            )

        assert result["label"] == "invoice"
        mock_result.get_document_parse_result.assert_awaited_once_with(DOCUMENT_ID, tenant_id=TENANT_ID)
        mock_result.create_result.assert_awaited_once()
        assert [call.args[1] for call in mock_update.await_args_list] == ["llm", "completed"]

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
    async def test_extract_handler_delegates_to_extract_service(self):
        """Extract handler 委托给 services.extract_service（#32 v3.1）。"""
        from services.job_runner import handle_extract_job

        job = _job()
        revision = {"id": REVISION_ID}
        configuration = {"type": "extract"}

        with patch(
            "services.extract_service.handle_extract_job",
            new_callable=AsyncMock,
            return_value={"report_no": "WT-1"},
        ) as mock_handle:
            result = await handle_extract_job(
                job=job, revision=revision, configuration=configuration
            )

        assert result == {"report_no": "WT-1"}
        mock_handle.assert_awaited_once_with(job, revision, configuration)
