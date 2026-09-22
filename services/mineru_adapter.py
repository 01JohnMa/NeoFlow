# services/mineru_adapter.py
"""MinerU 托管 API ParserAdapter（官方 v4 接口）。

流程（本地文件）：
1. POST {base}/api/v4/file-urls/batch 申请上传链接（Bearer token）；
2. PUT 文件到返回的 OSS 链接，MinerU 自动排队解析；
3. GET {base}/api/v4/extract-results/batch/{batch_id} 轮询到 done；
4. 下载 full_zip_url 并归一化为 ParseResult。

API 形态依据官方文档 https://mineru.net/apiManage/docs（v4）与 2026-09 实测：
zip 内含 full.md、*_content_list.json、layout.json（即 middle.json 等价物）、images。
本地 4090 的 hybrid-engine/hybrid-http-client 后续以同一 ParseResult 契约另行接入。
"""

import asyncio
import hashlib
import io
import os
import re
import tempfile
import time
import zipfile
from typing import Any, Dict, Optional, Tuple

import httpx
from loguru import logger

from config.settings import settings
from services.mineru_normalizer import normalize_mineru_output
from services.parser_adapter import ParserAdapter, ParserAdapterError
from services.parse_result import ParseResult

def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

DEFAULT_MODEL_VERSION = "pipeline"
DEFAULT_LANGUAGE = "ch"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 300

UPLOAD_URL_PATH = "/api/v4/file-urls/batch"
RESULT_PATH = "/api/v4/extract-results/batch/{batch_id}"

TERMINAL_STATES = ("done", "failed")
_PAGE_RANGE_TOKEN = re.compile(r"^(\d+)(?:-(\d+))?$")


class MinerUApiError(ParserAdapterError):
    """调用 MinerU 托管 API 失败。"""


def _requested_physical_pages(page_ranges: Any) -> Optional[list[int]]:
    """Expand a page-range request in the stable physical order sent to MinerU."""
    if not page_ranges:
        return None
    pages: set[int] = set()
    for raw in str(page_ranges).split(","):
        match = _PAGE_RANGE_TOKEN.match(raw.strip())
        if not match:
            return None
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if end < start:
            return None
        pages.update(range(start, end + 1))
    return sorted(pages)


def _restore_requested_page_identity(result: ParseResult, page_ranges: Any) -> None:
    """Restore physical page numbers when a selected-page provider renumbers output.

    MinerU's selected-page response currently returns pages in request order but
    numbers them from one again. Evidence and downstream routing use source
    physical page numbers, so silently accepting those local positions would
    attach evidence to the wrong source page. Refuse an ambiguous cardinality
    instead of guessing a mapping.
    """
    requested = _requested_physical_pages(page_ranges)
    if requested is None:
        return
    if len(result.pages) != len(requested):
        raise MinerUApiError(
            "按页解析返回页数与请求物理页数不一致，无法安全恢复页码: "
            f"requested={len(requested)}, returned={len(result.pages)}"
        )
    for page, physical_page_no in zip(result.pages, requested):
        page.page_no = physical_page_no
    coverage = result.engine.setdefault("coverage", {})
    old_states = coverage.get("page_states") or {}
    coverage["requested_page_numbers"] = requested
    coverage["reported_pages"] = requested
    coverage["observed_page_numbers"] = sorted(
        physical_page_no
        for physical_page_no, page in zip(requested, result.pages)
        if page.blocks
    )
    coverage["page_states"] = {
        str(physical_page_no): old_states.get(str(index), "unknown")
        for index, physical_page_no in enumerate(requested, start=1)
    }


def build_batch_payload(file_name: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """构建 file-urls/batch 请求体。

    method（auto/txt/ocr，对应本地 --method）在托管 API 上映射为 is_ocr：
    仅 method=ocr 时显式开启，其余交给服务端自动判定。
    """
    params = dict(params or {})
    file_entry: Dict[str, Any] = {"name": file_name}
    if params.get("data_id"):
        file_entry["data_id"] = params["data_id"]
    if params.get("page_ranges"):
        file_entry["page_ranges"] = params["page_ranges"]
    if str(params.get("method") or "auto").lower() == "ocr":
        file_entry["is_ocr"] = True

    payload: Dict[str, Any] = {
        "files": [file_entry],
        "model_version": params.get("model_version") or DEFAULT_MODEL_VERSION,
        "language": params.get("language") or DEFAULT_LANGUAGE,
        "enable_formula": bool(params.get("enable_formula", True)),
        "enable_table": bool(params.get("enable_table", True)),
    }
    if params.get("extra_formats"):
        payload["extra_formats"] = params["extra_formats"]
    return payload


def _extract_zip_bytes(data: bytes, target_dir: str) -> None:
    """解压 MinerU 结果 zip，拒绝逃逸出目标目录的成员。"""
    real_target = os.path.realpath(target_dir)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in archive.infolist():
            member_path = os.path.realpath(os.path.join(real_target, member.filename))
            if member_path != real_target and not member_path.startswith(real_target + os.sep):
                raise MinerUApiError(f"MinerU zip 包含非法路径: {member.filename}")
        archive.extractall(real_target)


class MinerUApiAdapter(ParserAdapter):
    """MinerU 托管 API 适配器。"""

    name = "mineru"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        poll_interval: Optional[float] = None,
        timeout: Optional[float] = None,
    ):
        self._api_key = settings.MINERU_API_KEY if api_key is None else api_key
        self._base_url = (base_url or settings.MINERU_BASE_URL).rstrip("/")
        self._poll_interval = (
            settings.MINERU_POLL_INTERVAL_SECONDS if poll_interval is None else poll_interval
        )
        self._timeout = (
            settings.MINERU_PARSE_TIMEOUT_SECONDS if timeout is None else timeout
        )

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "*/*",
        }

    async def parse(
        self,
        file_path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> ParseResult:
        params = dict(params or {})
        if not self._api_key:
            raise MinerUApiError("未配置 MINERU_API_KEY，无法调用 MinerU 托管 API")
        if not file_path or not os.path.isfile(file_path):
            raise MinerUApiError(f"待解析文件不存在: {file_path}")

        file_name = os.path.basename(file_path)
        source_hash_before = _file_sha256(file_path)
        request_timeout = float(
            params.get("request_timeout_seconds") or DEFAULT_REQUEST_TIMEOUT_SECONDS
        )
        async with httpx.AsyncClient(
            timeout=request_timeout,
            follow_redirects=True,
        ) as client:
            batch_id, upload_url = await self._apply_upload_url(client, file_name, params)
            await self._upload(client, upload_url, file_path)
            task = await self._wait_for_result(client, batch_id, params)
            if task.get("state") != "done":
                reason = task.get("err_msg") or task.get("state") or "未知错误"
                raise MinerUApiError(f"MinerU 解析失败: {reason}")
            zip_url = task.get("full_zip_url")
            if not zip_url:
                raise MinerUApiError("MinerU 解析完成但未返回 full_zip_url")

            with tempfile.TemporaryDirectory(prefix="neoflow-mineru-") as workdir:
                await self._download_and_extract(client, zip_url, workdir)
                result = await asyncio.to_thread(normalize_mineru_output, workdir, params)

        _restore_requested_page_identity(result, params.get("page_ranges"))

        source_hash_after = _file_sha256(file_path)
        result.engine["source_document_hash"] = (
            source_hash_before if source_hash_before == source_hash_after else None
        )
        if source_hash_before != source_hash_after:
            result.warnings.append("源文件在解析期间发生变化，source_document_hash 不可用")

        logger.info(
            f"MinerU 解析完成: file={file_name} pages={len(result.pages)} "
            f"warnings={len(result.warnings)}"
        )
        return result

    # ============ 内部步骤（测试可单独替换） ============

    async def _apply_upload_url(
        self,
        client: httpx.AsyncClient,
        file_name: str,
        params: Dict[str, Any],
    ) -> Tuple[str, str]:
        response = await client.post(
            f"{self._base_url}{UPLOAD_URL_PATH}",
            headers=self._headers(),
            json=build_batch_payload(file_name, params),
        )
        data = self._parse_response(response, "申请上传链接")
        batch_id = data.get("batch_id")
        upload_urls = data.get("file_urls") or []
        if not batch_id or not upload_urls:
            raise MinerUApiError("MinerU 未返回 batch_id/file_urls")
        return str(batch_id), str(upload_urls[0])

    async def _upload(
        self,
        client: httpx.AsyncClient,
        upload_url: str,
        file_path: str,
    ) -> None:
        with open(file_path, "rb") as handle:
            content = handle.read()
        response = await client.put(upload_url, content=content)
        if response.status_code >= 400:
            raise MinerUApiError(f"MinerU 文件上传失败: HTTP {response.status_code}")

    async def _wait_for_result(
        self,
        client: httpx.AsyncClient,
        batch_id: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        timeout = float(params.get("timeout_seconds") or self._timeout)
        poll_interval = float(params.get("poll_interval_seconds") or self._poll_interval)
        data_id = params.get("data_id")
        deadline = time.monotonic() + timeout

        while True:
            response = await client.get(
                f"{self._base_url}{RESULT_PATH.format(batch_id=batch_id)}",
                headers=self._headers(),
            )
            data = self._parse_response(response, "查询解析结果")
            results = data.get("extract_result") or []
            task = None
            if data_id:
                task = next((item for item in results if item.get("data_id") == data_id), None)
            if task is None and results:
                task = results[0]

            if task and task.get("state") in TERMINAL_STATES:
                return task
            if time.monotonic() >= deadline:
                state = (task or {}).get("state") or "unknown"
                raise MinerUApiError(f"MinerU 轮询超时（{timeout:.0f}s），最后状态: {state}")
            await asyncio.sleep(poll_interval)

    async def _download_and_extract(
        self,
        client: httpx.AsyncClient,
        zip_url: str,
        target_dir: str,
    ) -> None:
        response = await client.get(zip_url)
        if response.status_code >= 400:
            raise MinerUApiError(f"下载 MinerU 结果失败: HTTP {response.status_code}")
        await asyncio.to_thread(_extract_zip_bytes, response.content, target_dir)

    @staticmethod
    def _parse_response(response: httpx.Response, action: str) -> Dict[str, Any]:
        if response.status_code >= 400:
            raise MinerUApiError(f"MinerU {action}失败: HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise MinerUApiError(f"MinerU {action}返回非 JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise MinerUApiError(f"MinerU {action}返回结构异常")
        if payload.get("code") not in (0, None):
            raise MinerUApiError(
                f"MinerU {action}失败: code={payload.get('code')} msg={payload.get('msg')}"
            )
        return payload.get("data") or {}
