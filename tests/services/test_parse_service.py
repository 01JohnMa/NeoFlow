# tests/services/test_parse_service.py
"""Parse Job handler 测试 — 参数化执行规格、Result 落库、Job 状态推进。"""

from unittest.mock import AsyncMock, patch

import pytest

from services.parse_result import Block, Page, ParseResult
from tests.conftest import DOCUMENT_ID, TENANT_ID

JOB_ID = "99999999-9999-4999-8999-999999999999"


def _job(**overrides):
    job = {
        "job_id": JOB_ID,
        "document_ids": [DOCUMENT_ID],
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
