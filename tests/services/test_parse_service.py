# tests/services/test_parse_service.py
"""Parse Job handler 测试 — 参数合并、适配器调用、Result 落库、Job 状态推进。"""

from unittest.mock import AsyncMock, patch

import pytest

from services.parse_result import Block, Page, ParseResult
from tests.conftest import DOCUMENT_ID, TENANT_ID

JOB_ID = "99999999-9999-4999-8999-999999999999"
REVISION_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"


def _job(**overrides):
    job = {
        "job_id": JOB_ID,
        "job_type": "parse",
        "document_ids": [DOCUMENT_ID],
        "configuration_revision_id": REVISION_ID,
        "tenant_id": TENANT_ID,
    }
    job.update(overrides)
    return job


def _document(**overrides):
    document = {
        "id": DOCUMENT_ID,
        "tenant_id": TENANT_ID,
        "file_path": "/tmp/demo.pdf",
    }
    document.update(overrides)
    return document


def _parse_result():
    return ParseResult(
        pages=[Page(page_no=1, width=100, height=200, blocks=[
            Block(id="p1-b1", type="text", bbox=[0, 0, 10, 10], reading_order=1,
                  text="hello", source="native-text"),
        ])],
        markdown="hello",
        engine={"name": "mineru", "backend": "pipeline"},
    )


class TestBuildParseParams:
    def test_defaults_when_definition_missing(self):
        from services.parse_service import build_parse_params

        params = build_parse_params()

        assert params["backend"] == "mineru-api"
        assert params["model_version"] == "pipeline"
        assert params["method"] == "auto"
        assert params["effort"] == "medium"

    def test_revision_section_overrides_defaults(self):
        from services.parse_service import build_parse_params

        params = build_parse_params(revision={
            "definition": {"parse": {"model_version": "vlm", "method": "ocr"}},
        })

        assert params["model_version"] == "vlm"
        assert params["method"] == "ocr"
        assert params["backend"] == "mineru-api"

    def test_configuration_draft_used_without_revision(self):
        from services.parse_service import build_parse_params

        params = build_parse_params(configuration={
            "draft_definition": {"parse": {"effort": "high"}},
        })

        assert params["effort"] == "high"


class TestHandleParseJob:
    @pytest.mark.asyncio
    async def test_success_stores_parse_result_and_completes_job(self):
        from services.parse_service import handle_parse_job

        adapter = AsyncMock()
        adapter.parse = AsyncMock(return_value=_parse_result())

        with patch("services.parse_service.get_parser_adapter", return_value=adapter), \
             patch("services.parse_service.result_service") as mock_result, \
             patch("services.supabase_service.supabase_service") as mock_supabase, \
             patch("api.jobs.update_job", new_callable=AsyncMock) as mock_update:
            mock_supabase.get_document = AsyncMock(return_value=_document())
            mock_result.record_parse_result = AsyncMock(return_value={"id": "r-1"})

            result = await handle_parse_job(
                job=_job(),
                revision={"definition": {"parse": {"model_version": "vlm"}}},
                configuration={"type": "parse"},
            )

        assert result is not None
        adapter.parse.assert_awaited_once()
        parsed_kwargs = adapter.parse.await_args.args
        assert parsed_kwargs[0] == "/tmp/demo.pdf"
        assert parsed_kwargs[1]["model_version"] == "vlm"
        assert parsed_kwargs[1]["backend"] == "mineru-api"
        stored_kwargs = mock_result.record_parse_result.await_args.kwargs
        assert stored_kwargs["tenant_id"] == TENANT_ID
        assert stored_kwargs["document_id"] == DOCUMENT_ID
        assert stored_kwargs["job_id"] == JOB_ID
        assert stored_kwargs["config_revision_id"] == REVISION_ID
        assert stored_kwargs["parse_data"]["markdown"] == "hello"
        assert [call.args[1] for call in mock_update.await_args_list] == [
            "parsing", "saving", "completed",
        ]

    @pytest.mark.asyncio
    async def test_missing_document_marks_job_failed(self):
        from services.parse_service import handle_parse_job

        with patch("services.parse_service.get_parser_adapter") as mock_adapter_factory, \
             patch("services.supabase_service.supabase_service") as mock_supabase, \
             patch("api.jobs.update_job", new_callable=AsyncMock) as mock_update:
            mock_supabase.get_document = AsyncMock(return_value=None)

            result = await handle_parse_job(job=_job())

        assert result is None
        mock_update.assert_awaited_once()
        assert mock_update.await_args.args[1] == "failed"
        mock_adapter_factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_adapter_failure_marks_job_failed(self):
        from services.parse_service import handle_parse_job

        adapter = AsyncMock()
        adapter.parse = AsyncMock(side_effect=RuntimeError("MinerU 挂了"))

        with patch("services.parse_service.get_parser_adapter", return_value=adapter), \
             patch("services.parse_service.result_service") as mock_result, \
             patch("services.supabase_service.supabase_service") as mock_supabase, \
             patch("api.jobs.update_job", new_callable=AsyncMock) as mock_update:
            mock_supabase.get_document = AsyncMock(return_value=_document())
            mock_result.record_parse_result = AsyncMock()

            result = await handle_parse_job(job=_job())

        assert result is None
        assert mock_update.await_args_list[-1].args[1] == "failed"
        assert "MinerU 挂了" in mock_update.await_args_list[-1].kwargs["error"]
        mock_result.record_parse_result.assert_not_called()

    @pytest.mark.asyncio
    async def test_result_write_failure_marks_job_failed(self):
        from services.parse_service import handle_parse_job

        adapter = AsyncMock()
        adapter.parse = AsyncMock(return_value=_parse_result())

        with patch("services.parse_service.get_parser_adapter", return_value=adapter), \
             patch("services.parse_service.result_service") as mock_result, \
             patch("services.supabase_service.supabase_service") as mock_supabase, \
             patch("api.jobs.update_job", new_callable=AsyncMock) as mock_update:
            mock_supabase.get_document = AsyncMock(return_value=_document())
            mock_result.record_parse_result = AsyncMock(return_value=None)

            result = await handle_parse_job(job=_job())

        assert result is None
        assert mock_update.await_args_list[-1].args[1] == "failed"

    @pytest.mark.asyncio
    async def test_multiple_documents_each_get_result(self):
        from services.parse_service import handle_parse_job

        second_document_id = "77777777-7777-4777-8777-777777777777"
        adapter = AsyncMock()
        adapter.parse = AsyncMock(return_value=_parse_result())
        documents = {
            DOCUMENT_ID: _document(),
            second_document_id: _document(id=second_document_id, file_path="/tmp/demo2.pdf"),
        }

        async def fake_get_document(document_id):
            return documents.get(document_id)

        with patch("services.parse_service.get_parser_adapter", return_value=adapter), \
             patch("services.parse_service.result_service") as mock_result, \
             patch("services.supabase_service.supabase_service") as mock_supabase, \
             patch("api.jobs.update_job", new_callable=AsyncMock) as mock_update:
            mock_supabase.get_document = AsyncMock(side_effect=fake_get_document)
            mock_result.record_parse_result = AsyncMock(return_value={"id": "r-1"})

            result = await handle_parse_job(
                job=_job(document_ids=[DOCUMENT_ID, second_document_id])
            )

        assert result is not None
        assert adapter.parse.await_count == 2
        assert [call.args[0] for call in adapter.parse.await_args_list] == [
            "/tmp/demo.pdf",
            "/tmp/demo2.pdf",
        ]
        stored_documents = [
            call.kwargs["document_id"]
            for call in mock_result.record_parse_result.await_args_list
        ]
        assert stored_documents == [DOCUMENT_ID, second_document_id]
        assert mock_update.await_args_list[-1].args[1] == "completed"


class TestEnsureParseResult:
    @pytest.mark.asyncio
    async def test_returns_existing_parse_data(self):
        from services.parse_service import ensure_parse_result

        with patch("services.parse_service.result_service") as mock_result, \
             patch("services.parse_service.get_parser_adapter") as mock_adapter:
            mock_result.get_document_parse_result = AsyncMock(
                return_value={"data": {"markdown": "已有解析"}}
            )

            result = await ensure_parse_result(
                document_id=DOCUMENT_ID,
                file_path="/tmp/demo.pdf",
                tenant_id=TENANT_ID,
            )

        assert result == {"markdown": "已有解析"}
        mock_adapter.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_parses_when_missing_and_key_configured(self):
        from services.parse_service import ensure_parse_result

        adapter = AsyncMock()
        adapter.parse = AsyncMock(return_value=_parse_result())

        with patch("services.parse_service.result_service") as mock_result, \
             patch("services.parse_service.get_parser_adapter", return_value=adapter), \
             patch("services.parse_service.settings") as mock_settings:
            mock_settings.MINERU_API_KEY = "test-key"
            mock_result.get_document_parse_result = AsyncMock(return_value=None)
            mock_result.record_parse_result = AsyncMock(return_value={"id": "r-parse"})

            result = await ensure_parse_result(
                document_id=DOCUMENT_ID,
                file_path="/tmp/demo.pdf",
                tenant_id=TENANT_ID,
            )

        assert result["markdown"] == "hello"
        adapter.parse.assert_awaited_once()
        assert mock_result.record_parse_result.await_args.kwargs["document_id"] == DOCUMENT_ID

    @pytest.mark.asyncio
    async def test_uses_configured_parse_section(self):
        from services.parse_service import ensure_parse_result

        adapter = AsyncMock()
        adapter.parse = AsyncMock(return_value=_parse_result())

        with patch("services.parse_service.result_service") as mock_result, \
             patch("services.parse_service.get_parser_adapter", return_value=adapter), \
             patch("services.parse_service.settings") as mock_settings:
            mock_settings.MINERU_API_KEY = "test-key"
            mock_result.get_document_parse_result = AsyncMock(return_value=None)
            mock_result.record_parse_result = AsyncMock(return_value={"id": "r"})

            await ensure_parse_result(
                document_id=DOCUMENT_ID,
                file_path="/tmp/demo.pdf",
                tenant_id=TENANT_ID,
                parse_section={"model_version": "vlm", "method": "ocr"},
            )

        params = adapter.parse.await_args.args[1]
        assert params["model_version"] == "vlm"
        assert params["method"] == "ocr"

    @pytest.mark.asyncio
    async def test_returns_none_without_mineru_key(self):
        from services.parse_service import ensure_parse_result

        with patch("services.parse_service.result_service") as mock_result, \
             patch("services.parse_service.get_parser_adapter") as mock_adapter, \
             patch("services.parse_service.settings") as mock_settings:
            mock_settings.MINERU_API_KEY = ""
            mock_result.get_document_parse_result = AsyncMock(return_value=None)

            result = await ensure_parse_result(
                document_id=DOCUMENT_ID,
                file_path="/tmp/demo.pdf",
                tenant_id=TENANT_ID,
            )

        assert result is None
        mock_adapter.assert_not_called()


class TestEnsureParseRevision:
    @pytest.mark.asyncio
    async def test_creates_and_publishes_system_configuration(self):
        from services.parse_service import ensure_parse_revision

        with patch("services.configuration_service.configuration_service") as mock_config:
            mock_config.list_configurations = AsyncMock(return_value=[])
            mock_config.create_configuration = AsyncMock(return_value={"id": "config-1"})
            mock_config.publish_configuration = AsyncMock(
                return_value={"revision": {"id": "rev-1", "revision_number": 1}}
            )

            revision = await ensure_parse_revision(TENANT_ID, "vlm", created_by="user-1")

        assert revision["id"] == "rev-1"
        created = mock_config.create_configuration.await_args.args[0]
        assert created["type"] == "parse"
        assert created["definition"]["parse"]["model_version"] == "vlm"
        mock_config.publish_configuration.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_current_revision_when_mode_matches(self):
        from services.parse_service import ensure_parse_revision

        current = {
            "id": "rev-1",
            "definition": {"parse": {"model_version": "pipeline"}},
        }
        with patch("services.configuration_service.configuration_service") as mock_config:
            mock_config.list_configurations = AsyncMock(
                return_value=[{"id": "config-1", "code": "__system_parse__"}]
            )
            mock_config.get_configuration_detail = AsyncMock(
                return_value={"current_revision": current}
            )
            mock_config.update_configuration = AsyncMock()
            mock_config.publish_configuration = AsyncMock()

            revision = await ensure_parse_revision(TENANT_ID, "pipeline")

        assert revision == current
        mock_config.update_configuration.assert_not_awaited()
        mock_config.publish_configuration.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_publishes_new_revision_on_mode_change(self):
        from services.parse_service import ensure_parse_revision

        with patch("services.configuration_service.configuration_service") as mock_config:
            mock_config.list_configurations = AsyncMock(
                return_value=[{"id": "config-1", "code": "__system_parse__"}]
            )
            mock_config.get_configuration_detail = AsyncMock(
                return_value={
                    "current_revision": {
                        "id": "rev-1",
                        "definition": {"parse": {"model_version": "pipeline"}},
                    }
                }
            )
            mock_config.update_configuration = AsyncMock(return_value={"id": "config-1"})
            mock_config.publish_configuration = AsyncMock(
                return_value={"revision": {"id": "rev-2", "revision_number": 2}}
            )

            revision = await ensure_parse_revision(TENANT_ID, "vlm")

        assert revision["id"] == "rev-2"
        updated_definition = mock_config.update_configuration.await_args.args[1]
        assert updated_definition["definition"]["parse"]["model_version"] == "vlm"
        mock_config.publish_configuration.assert_awaited_once()


class TestParameterizedParseJob:
    """execution_spec 路径：单文件、冻结参数、认领感知、原子交卷。"""

    def _spec_job(self, **spec_overrides):
        spec = {
            "capability": "parse",
            "spec_version": "1",
            "effective_params": {"model_version": "vlm", "backend": "mineru-api"},
        }
        spec.update(spec_overrides)
        return _job(
            configuration_revision_id=None,
            locked_by="worker-1",
            attempts=2,
            execution_spec=spec,
        )

    @pytest.mark.asyncio
    async def test_uses_frozen_params_and_commits_result(self):
        from services.parse_service import handle_parse_job

        adapter = AsyncMock()
        adapter.parse = AsyncMock(return_value=_parse_result())
        job = self._spec_job()

        with patch("services.parse_service.get_parser_adapter", return_value=adapter) as mock_adapter, \
             patch("services.supabase_service.supabase_service") as mock_supabase, \
             patch("api.jobs.update_job_if_owned", new_callable=AsyncMock) as mock_owned, \
             patch("api.jobs.commit_parse_job", new_callable=AsyncMock) as mock_commit:
            mock_supabase.get_document = AsyncMock(return_value=_document())
            mock_owned.return_value = True
            mock_commit.return_value = "completed"

            result = await handle_parse_job(job)

        assert result is not None
        # worker 只读冻结参数，不回退当前默认值
        mock_adapter.assert_called_once_with(job["execution_spec"]["effective_params"])
        mock_commit.assert_awaited_once()
        assert mock_commit.await_args.args[3] == "ok"
        assert mock_commit.await_args.kwargs["parse_data"]["markdown"] == "hello"

    @pytest.mark.asyncio
    async def test_remove_watermark_filters_before_commit(self):
        from services.parse_service import handle_parse_job

        result = _parse_result()
        result.pages[0].blocks.append(Block(
            id="p1-b2", type="text", bbox=[0, 10, 10, 20], reading_order=2,
            text="COPY", source="native-text",
        ))
        result.markdown = "hello\nCOPY"

        adapter = AsyncMock()
        adapter.parse = AsyncMock(return_value=result)
        job = self._spec_job(effective_params={
            "model_version": "vlm",
            "backend": "mineru-api",
            "remove_watermark": True,
            "watermark_keywords": ["COPY"],
        })

        with patch("services.parse_service.get_parser_adapter", return_value=adapter), \
             patch("services.supabase_service.supabase_service") as mock_supabase, \
             patch("api.jobs.update_job_if_owned", new_callable=AsyncMock) as mock_owned, \
             patch("api.jobs.commit_parse_job", new_callable=AsyncMock) as mock_commit:
            mock_supabase.get_document = AsyncMock(return_value=_document())
            mock_owned.return_value = True
            mock_commit.return_value = "completed"

            returned = await handle_parse_job(job)

        assert returned is not None
        parse_data = mock_commit.await_args.kwargs["parse_data"]
        assert parse_data["markdown"] == "hello"
        assert [block["text"] for block in parse_data["pages"][0]["blocks"]] == ["hello"]
        assert parse_data["engine"]["watermark_filter"]["mode"] == "keywords"
        assert parse_data["engine"]["watermark_filter"]["removed_blocks"] == 1

    @pytest.mark.asyncio
    async def test_remove_watermark_without_keywords_auto_detects_repeats(self):
        from services.parse_service import handle_parse_job

        result = ParseResult(
            pages=[
                Page(page_no=1, width=100, height=200, blocks=[
                    _parse_result().pages[0].blocks[0],
                    Block(id="p1-b2", type="text", bbox=[0, 10, 10, 20], reading_order=2,
                          text="COPY", source="native-text"),
                ]),
                Page(page_no=2, width=100, height=200, blocks=[
                    Block(id="p2-b1", type="text", bbox=[0, 0, 10, 10], reading_order=1,
                          text="COPY", source="native-text"),
                ]),
                Page(page_no=3, width=100, height=200, blocks=[
                    Block(id="p3-b1", type="text", bbox=[0, 0, 10, 10], reading_order=1,
                          text="copy", source="native-text"),
                ]),
            ],
            markdown="hello\nCOPY",
            engine={"name": "mineru"},
        )
        adapter = AsyncMock()
        adapter.parse = AsyncMock(return_value=result)
        job = self._spec_job(effective_params={
            "model_version": "pipeline",
            "backend": "mineru-api",
            "remove_watermark": True,
            "watermark_keywords": [],
        })

        with patch("services.parse_service.get_parser_adapter", return_value=adapter), \
             patch("services.supabase_service.supabase_service") as mock_supabase, \
             patch("api.jobs.update_job_if_owned", new_callable=AsyncMock) as mock_owned, \
             patch("api.jobs.commit_parse_job", new_callable=AsyncMock) as mock_commit:
            mock_supabase.get_document = AsyncMock(return_value=_document())
            mock_owned.return_value = True
            mock_commit.return_value = "completed"

            returned = await handle_parse_job(job)

        assert returned is not None
        parse_data = mock_commit.await_args.kwargs["parse_data"]
        assert parse_data["markdown"] == "hello"
        remaining = [
            block["text"]
            for page in parse_data["pages"]
            for block in page["blocks"]
        ]
        assert remaining == ["hello"]
        assert parse_data["engine"]["watermark_filter"] == {
            "mode": "auto",
            "removed_blocks": 3,
            "removed_lines": 1,
            "auto_texts": ["copy"],
        }

    @pytest.mark.asyncio
    async def test_adapter_failure_commits_failed_without_product(self):
        from services.parse_service import handle_parse_job

        adapter = AsyncMock()
        adapter.parse = AsyncMock(side_effect=RuntimeError("mineru timeout"))
        job = self._spec_job()

        with patch("services.parse_service.get_parser_adapter", return_value=adapter), \
             patch("services.supabase_service.supabase_service") as mock_supabase, \
             patch("api.jobs.update_job_if_owned", new_callable=AsyncMock) as mock_owned, \
             patch("api.jobs.commit_parse_job", new_callable=AsyncMock) as mock_commit:
            mock_supabase.get_document = AsyncMock(return_value=_document())
            mock_owned.return_value = True
            mock_commit.return_value = "failed"

            result = await handle_parse_job(job)

        assert result is None
        mock_commit.assert_awaited_once()
        assert mock_commit.await_args.args[3] == "failed"

    @pytest.mark.asyncio
    async def test_lost_claim_before_commit_writes_no_product(self):
        from services.parse_service import handle_parse_job

        adapter = AsyncMock()
        adapter.parse = AsyncMock(return_value=_parse_result())
        job = self._spec_job()

        with patch("services.parse_service.get_parser_adapter", return_value=adapter), \
             patch("services.supabase_service.supabase_service") as mock_supabase, \
             patch("api.jobs.update_job_if_owned", new_callable=AsyncMock) as mock_owned, \
             patch("api.jobs.commit_parse_job", new_callable=AsyncMock) as mock_commit:
            mock_supabase.get_document = AsyncMock(return_value=_document())
            mock_owned.return_value = False

            result = await handle_parse_job(job)

        assert result is None
        mock_owned.assert_awaited_once()
        mock_commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unsupported_spec_version_fails_closed(self):
        from services.parse_service import handle_parse_job

        job = self._spec_job(spec_version="99")

        with patch("services.parse_service.get_parser_adapter") as mock_adapter, \
             patch("services.supabase_service.supabase_service"), \
             patch("api.jobs.commit_parse_job", new_callable=AsyncMock) as mock_commit:
            mock_commit.return_value = "failed"
            result = await handle_parse_job(job)

        assert result is None
        mock_adapter.assert_not_called()
        mock_commit.assert_awaited_once()
        assert "99" in mock_commit.await_args.kwargs["error"]
