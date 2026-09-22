# tests/services/test_parser_adapter.py
"""ParserAdapter 接口 + MinerU 托管 API 适配测试（HTTP 全部打桩，不联网）。"""

import shutil
from pathlib import Path
from typing import Any, List
from unittest.mock import AsyncMock, patch

import pytest

from services.parser_adapter import (
    ParserAdapter,
    ParserAdapterError,
    get_parser_adapter,
)
from services.parse_result import Page, ParseResult

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "mineru"


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: Any = None, content: bytes = b""):
        self.status_code = status_code
        self._payload = payload
        self.content = content

    def json(self):
        return self._payload


class _RecordingClient:
    def __init__(self, response: _FakeResponse):
        self.response = response
        self.calls: List[tuple] = []

    async def post(self, url, headers=None, json=None):
        self.calls.append(("post", url, headers, json))
        return self.response

    async def put(self, url, content=None):
        self.calls.append(("put", url, content))
        return self.response

    async def get(self, url, headers=None):
        self.calls.append(("get", url, headers))
        return self.response


class TestAdapterRegistry:
    def test_default_backend_is_mineru_api(self):
        adapter = get_parser_adapter()
        assert adapter.name == "mineru"

    def test_unknown_backend_rejected(self):
        with pytest.raises(ParserAdapterError):
            get_parser_adapter({"backend": "nope"})

    def test_reserved_local_backend_rejected_with_clear_message(self):
        with pytest.raises(ParserAdapterError, match="本地 MinerU 后端尚未接入"):
            get_parser_adapter({"backend": "hybrid-engine"})

    def test_interface_requires_parse(self):
        with pytest.raises(TypeError):
            ParserAdapter()


class TestBatchPayload:
    def test_defaults(self):
        from services.mineru_adapter import build_batch_payload

        payload = build_batch_payload("demo.pdf", {})

        assert payload["files"] == [{"name": "demo.pdf"}]
        assert payload["model_version"] == "pipeline"
        assert payload["language"] == "ch"
        assert payload["enable_formula"] is True
        assert payload["enable_table"] is True
        assert "extra_formats" not in payload

    def test_method_ocr_maps_to_is_ocr(self):
        from services.mineru_adapter import build_batch_payload

        payload = build_batch_payload("demo.pdf", {"method": "ocr", "model_version": "vlm"})
        assert payload["files"][0]["is_ocr"] is True
        assert payload["model_version"] == "vlm"

        auto_payload = build_batch_payload("demo.pdf", {"method": "auto"})
        assert "is_ocr" not in auto_payload["files"][0]

    def test_page_ranges_data_id_and_extra_formats(self):
        from services.mineru_adapter import build_batch_payload

        payload = build_batch_payload("demo.pdf", {
            "data_id": "doc-1",
            "page_ranges": "1-3",
            "extra_formats": ["docx"],
            "enable_formula": False,
        })

        assert payload["files"][0]["data_id"] == "doc-1"
        assert payload["files"][0]["page_ranges"] == "1-3"
        assert payload["extra_formats"] == ["docx"]
        assert payload["enable_formula"] is False


class TestHttpSteps:
    def _adapter(self):
        from services.mineru_adapter import MinerUApiAdapter

        return MinerUApiAdapter(
            api_key="test-key",
            base_url="https://mineru.test",
            poll_interval=0.01,
            timeout=30,
        )

    @pytest.mark.asyncio
    async def test_apply_upload_url_sends_bearer_and_payload(self):
        from services.mineru_adapter import build_batch_payload

        adapter = self._adapter()
        response = _FakeResponse(200, {
            "code": 0,
            "data": {"batch_id": "batch-1", "file_urls": ["https://upload.example/1"]},
        })
        client = _RecordingClient(response)
        params = {"model_version": "vlm", "method": "ocr"}

        batch_id, upload_url = await adapter._apply_upload_url(client, "demo.pdf", params)

        assert batch_id == "batch-1"
        assert upload_url == "https://upload.example/1"
        method, url, headers, body = client.calls[0]
        assert (method, url) == ("post", "https://mineru.test/api/v4/file-urls/batch")
        assert headers["Authorization"] == "Bearer test-key"
        assert body == build_batch_payload("demo.pdf", params)

    @pytest.mark.asyncio
    async def test_apply_upload_url_raises_on_api_error(self):
        from services.mineru_adapter import MinerUApiError

        adapter = self._adapter()
        client = _RecordingClient(_FakeResponse(200, {"code": -10002, "msg": "bad"}))

        with pytest.raises(MinerUApiError, match="bad"):
            await adapter._apply_upload_url(client, "demo.pdf", {})

    @pytest.mark.asyncio
    async def test_upload_puts_file_content(self, tmp_path):
        adapter = self._adapter()
        file_path = tmp_path / "demo.pdf"
        file_path.write_bytes(b"%PDF-1.4 test")
        client = _RecordingClient(_FakeResponse(200))

        await adapter._upload(client, "https://upload.example/1", str(file_path))

        method, url, content = client.calls[0]
        assert (method, url) == ("put", "https://upload.example/1")
        assert content == b"%PDF-1.4 test"

    @pytest.mark.asyncio
    async def test_wait_for_result_polls_until_done(self):
        adapter = self._adapter()
        running = _FakeResponse(200, {
            "code": 0,
            "data": {"extract_result": [{"state": "running"}]},
        })
        done = _FakeResponse(200, {
            "code": 0,
            "data": {"extract_result": [{"state": "done", "full_zip_url": "https://zip"}]},
        })

        class _SequencedClient:
            def __init__(self):
                self.responses = [running, done]
                self.calls = 0

            async def get(self, url, headers=None):
                self.calls += 1
                return self.responses.pop(0)

        client = _SequencedClient()
        with patch("services.mineru_adapter.asyncio.sleep", new=AsyncMock()):
            task = await adapter._wait_for_result(client, "batch-1", {})

        assert task["state"] == "done"
        assert client.calls == 2

    @pytest.mark.asyncio
    async def test_parse_response_rejects_http_error(self):
        from services.mineru_adapter import MinerUApiAdapter, MinerUApiError

        with pytest.raises(MinerUApiError, match="HTTP 500"):
            MinerUApiAdapter._parse_response(_FakeResponse(500), "查询解析结果")


class TestParseFlow:
    def _adapter(self):
        from services.mineru_adapter import MinerUApiAdapter

        return MinerUApiAdapter(api_key="test-key", base_url="https://mineru.test")

    @pytest.mark.asyncio
    async def test_parse_orchestrates_upload_poll_download_and_normalize(self, tmp_path):
        file_path = tmp_path / "demo.png"
        file_path.write_bytes(b"png-bytes")
        adapter = self._adapter()

        async def fake_download(client, zip_url, target_dir):
            shutil.copytree(FIXTURES / "pipeline", target_dir, dirs_exist_ok=True)

        apply_mock = AsyncMock(return_value=("batch-1", "https://upload.example/1"))
        with patch.object(adapter, "_apply_upload_url", new=apply_mock), \
             patch.object(adapter, "_upload", new=AsyncMock()) as upload_mock, \
             patch.object(adapter, "_wait_for_result", new=AsyncMock(
                 return_value={"state": "done", "full_zip_url": "https://zip"}
             )), \
             patch.object(adapter, "_download_and_extract", new=fake_download):
            result = await adapter.parse(str(file_path), {"model_version": "pipeline"})

        assert isinstance(result, ParseResult)
        assert result.pages[0].blocks[0].type == "header"
        assert apply_mock.await_args.args[1] == "demo.png"
        upload_mock.assert_awaited_once()
        assert upload_mock.await_args.args[1] == "https://upload.example/1"

    @pytest.mark.asyncio
    async def test_selected_pages_restore_physical_page_identity(self, tmp_path):
        from services.mineru_adapter import MinerUApiAdapter

        file_path = tmp_path / "demo.png"
        file_path.write_bytes(b"png-bytes")
        adapter = self._adapter()
        raw_result = ParseResult(
            pages=[
                Page(page_no=1, width=100, height=200),
                Page(page_no=2, width=100, height=200),
            ],
            engine={
                "coverage": {
                    "reported_pages": [1, 2],
                    "observed_page_numbers": [1, 2],
                    "page_states": {"1": "parsed", "2": "blank"},
                }
            },
        )

        async def fake_download(client, zip_url, target_dir):
            Path(target_dir, "unused").write_text("fixture")

        with patch.object(adapter, "_apply_upload_url", new=AsyncMock(
            return_value=("batch-1", "https://upload.example/1")
        )), patch.object(adapter, "_upload", new=AsyncMock()), \
             patch.object(adapter, "_wait_for_result", new=AsyncMock(
                 return_value={"state": "done", "full_zip_url": "https://zip"}
             )), patch.object(adapter, "_download_and_extract", new=fake_download), \
             patch("services.mineru_adapter.normalize_mineru_output", return_value=raw_result):
            result = await adapter.parse(str(file_path), {"page_ranges": "2,5"})

        assert [page.page_no for page in result.pages] == [2, 5]
        coverage = result.engine["coverage"]
        assert coverage["reported_pages"] == [2, 5]
        assert coverage["page_states"] == {"2": "parsed", "5": "blank"}

    @pytest.mark.asyncio
    async def test_parse_raises_without_api_key(self, tmp_path):
        from services.mineru_adapter import MinerUApiAdapter, MinerUApiError

        adapter = MinerUApiAdapter(api_key="", base_url="https://mineru.test")
        file_path = tmp_path / "demo.png"
        file_path.write_bytes(b"x")

        with pytest.raises(MinerUApiError, match="MINERU_API_KEY"):
            await adapter.parse(str(file_path))

    @pytest.mark.asyncio
    async def test_parse_raises_when_file_missing(self):
        from services.mineru_adapter import MinerUApiError

        with pytest.raises(MinerUApiError, match="文件不存在"):
            await self._adapter().parse("/tmp/not-a-real-file-8.png")

    @pytest.mark.asyncio
    async def test_parse_surfaces_failed_state(self, tmp_path):
        from services.mineru_adapter import MinerUApiError

        adapter = self._adapter()
        file_path = tmp_path / "demo.png"
        file_path.write_bytes(b"x")

        with patch.object(adapter, "_apply_upload_url", new=AsyncMock(
            return_value=("batch-1", "https://upload.example/1")
        )), patch.object(adapter, "_upload", new=AsyncMock()), \
             patch.object(adapter, "_wait_for_result", new=AsyncMock(
                 return_value={"state": "failed", "err_msg": "文件格式不支持"}
             )):
            with pytest.raises(MinerUApiError, match="文件格式不支持"):
                await adapter.parse(str(file_path))
