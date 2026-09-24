"""Build a per-Extract-Job page index from the uploaded source file.

This module deliberately owns no Document-level cache.  Its records live for
the current Extract execution only; a later Job builds its own index again.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import math
import os
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

import httpx

from config.settings import settings


class SourcePageIndexError(Exception):
    def __init__(self, reason: str, message: str = ""):
        super().__init__(f"{reason}: {message}" if message else reason)
        self.reason = reason
        self.message = message


def compact_page_ranges(pages: Sequence[int]) -> str:
    ordered = sorted(set(int(page) for page in pages))
    if not ordered:
        return ""
    parts: List[str] = []
    start = previous = ordered[0]
    for page in ordered[1:]:
        if page == previous + 1:
            previous = page
            continue
        parts.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = page
    parts.append(str(start) if start == previous else f"{start}-{previous}")
    return ",".join(parts)


@dataclass(frozen=True)
class SourcePage:
    page_no: int
    modality: str
    text: str = ""
    image_data_uri: Optional[str] = None


@dataclass(frozen=True)
class SourcePageIndex:
    source_hash: str
    pages: Sequence[SourcePage]
    vectors: Sequence[Sequence[float]]
    profile: str
    embedding_space: str = "text"


@dataclass(frozen=True)
class SourcePageCandidate:
    page_no: int
    score: float
    reasons: Sequence[str]


def _source_hash(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _page_count(path: str) -> int:
    try:
        output = subprocess.check_output(
            ["pdfinfo", path], text=True, stderr=subprocess.STDOUT, timeout=20
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SourcePageIndexError("source_page_count_failed", str(exc)) from exc
    for line in output.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise SourcePageIndexError("source_page_count_failed", "pdfinfo did not report Pages")


def _native_text(path: str, page_no: int) -> str:
    try:
        output = subprocess.check_output(
            ["pdftotext", "-f", str(page_no), "-l", str(page_no), "-layout", path, "-"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SourcePageIndexError("source_text_read_failed", f"page={page_no}: {exc}") from exc
    return " ".join(output.split())


def _render_page(path: str, page_no: int) -> str:
    with tempfile.TemporaryDirectory(prefix="neoflow-source-page-") as directory:
        prefix = str(Path(directory) / "page")
        try:
            subprocess.check_call(
                [
                    "pdftoppm",
                    "-f", str(page_no),
                    "-l", str(page_no),
                    "-png",
                    "-singlefile",
                    "-r", str(settings.SOURCE_PAGE_RENDER_DPI),
                    path,
                    prefix,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=60,
            )
            image_path = Path(prefix + ".png")
            if image_path.stat().st_size > min(settings.SOURCE_PAGE_MAX_IMAGE_BYTES, 5 * 1024 * 1024):
                raise SourcePageIndexError("source_image_too_large", f"page={page_no}")
            data = image_path.read_bytes()
        except (OSError, subprocess.SubprocessError) as exc:
            raise SourcePageIndexError("source_image_render_failed", f"page={page_no}: {exc}") from exc
    if len(data) > settings.SOURCE_PAGE_MAX_IMAGE_BYTES:
        raise SourcePageIndexError("source_image_too_large", f"page={page_no}")
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _validated_vectors(rows, count: int, dimension: Optional[int], reason: str):
    if not isinstance(rows, list) or len(rows) != count:
        raise SourcePageIndexError(reason, "batch cardinality")
    if any(not isinstance(row, dict) or type(row.get("index")) is not int for row in rows):
        raise SourcePageIndexError(reason, "invalid index")
    if sorted(row["index"] for row in rows) != list(range(count)):
        raise SourcePageIndexError(reason, "duplicate or missing index")
    vectors = []
    for row in sorted(rows, key=lambda row: row["index"]):
        vector = row.get("embedding")
        if (not isinstance(vector, list) or not vector
                or any(type(value) not in (float, int) or not math.isfinite(value) for value in vector)):
            raise SourcePageIndexError(reason, "non-finite or invalid vector")
        dimension = dimension or len(vector)
        if len(vector) != dimension or not math.isfinite(math.hypot(*vector)) or math.hypot(*vector) == 0:
            raise SourcePageIndexError(reason, "vector dimension or norm")
        vectors.append(vector)
    return vectors


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise SourcePageIndexError("source_embedding_space_mismatch")
    # Normalize first to avoid overflowing otherwise finite dot products.
    ln, rn = math.hypot(*left), math.hypot(*right)
    return sum((a / ln) * (b / rn) for a, b in zip(left, right))


async def _post(url, api_key, body, reason):
    try:
        async with httpx.AsyncClient(timeout=settings.EMBEDDING_TIMEOUT_SECONDS) as client:
            response = await client.post(url, headers={"Authorization": f"Bearer {api_key}"}, json=body)
    except httpx.HTTPError as exc:
        raise SourcePageIndexError(reason + "_failed", type(exc).__name__) from exc
    if response.status_code >= 400:
        raise SourcePageIndexError(reason + "_failed", f"HTTP {response.status_code}")
    try:
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("code"):
            raise ValueError("invalid payload")
        return payload
    except (TypeError, ValueError) as exc:
        raise SourcePageIndexError(reason + "_invalid", "invalid response") from exc


async def _openai_text_embeddings(inputs: Sequence[str], *, query: bool = False) -> List[List[float]]:
    if not settings.EMBEDDING_API_KEY or not settings.EMBEDDING_BASE_URL:
        raise SourcePageIndexError("source_text_embedding_unavailable")
    payload = await _post(settings.EMBEDDING_BASE_URL.rstrip("/") + "/embeddings", settings.EMBEDDING_API_KEY, {
        "model": settings.EMBEDDING_MODEL, "input": list(inputs), "encoding_format": "float",
        **({"dimensions": settings.EMBEDDING_DIMENSION} if settings.EMBEDDING_DIMENSION else {}),
    }, "source_text_embedding")
    return _validated_vectors(payload.get("data"), len(inputs), settings.EMBEDDING_DIMENSION or None, "source_text_embedding_invalid")


async def _dashscope_embeddings(contents: Sequence[dict]) -> List[List[float]]:
    if not settings.SOURCE_PAGE_IMAGE_API_KEY:
        raise SourcePageIndexError("source_image_embedding_unavailable")
    if settings.SOURCE_PAGE_IMAGE_MODEL != "qwen3-vl-embedding" or settings.SOURCE_PAGE_IMAGE_DIMENSION != 1024:
        raise SourcePageIndexError("source_image_profile_invalid", "requires qwen3-vl-embedding / 1024")
    if len(contents) > 20 or sum("image" in item for item in contents) > 1:
        raise SourcePageIndexError("source_image_request_too_large")
    payload = await _post(settings.SOURCE_PAGE_IMAGE_BASE_URL.rstrip("/") +
        "/api/v1/services/embeddings/multimodal-embedding/multimodal-embedding",
        settings.SOURCE_PAGE_IMAGE_API_KEY, {
            "model": "qwen3-vl-embedding", "input": {"contents": list(contents)},
            "parameters": {"dimension": 1024, "output_type": "dense", "enable_fusion": False},
        }, "source_image_embedding")
    output = payload.get("output")
    return _validated_vectors(output.get("embeddings") if isinstance(output, dict) else None,
                              len(contents), 1024, "source_image_embedding_invalid")


async def _dashscope_image_embeddings(contents: Sequence[str], *, query: bool = False) -> List[List[float]]:
    return await _dashscope_embeddings([{"image": value} for value in contents])


async def _dashscope_text_embeddings(contents: Sequence[str]) -> List[List[float]]:
    return await _dashscope_embeddings([{"text": value} for value in contents])


def _profile(space: str) -> str:
    # Cache/audit identity excludes credentials, includes preprocessing and provider settings.
    values = {"version": 2, "space": space, "min_text_chars": settings.SOURCE_PAGE_MIN_TEXT_CHARS,
              "dpi": settings.SOURCE_PAGE_RENDER_DPI, "max_image_bytes": min(settings.SOURCE_PAGE_MAX_IMAGE_BYTES, 5 * 1024 * 1024)}
    if space == "multimodal":
        values.update(endpoint=settings.SOURCE_PAGE_IMAGE_BASE_URL, model="qwen3-vl-embedding", dimension=1024, fusion=False)
    else:
        values.update(endpoint=settings.EMBEDDING_BASE_URL, model=settings.EMBEDDING_MODEL, dimension=settings.EMBEDDING_DIMENSION)
    return json.dumps(values, sort_keys=True, separators=(",", ":"))


async def build_source_page_index(file_path: str, *, request_gate=None) -> SourcePageIndex:
    """Job-local index; mixed documents use one multimodal space for ALL pages."""
    if not file_path or not os.path.isfile(file_path):
        raise SourcePageIndexError("source_file_unavailable", file_path)
    source_hash = await asyncio.to_thread(_source_hash, file_path)
    count = await asyncio.to_thread(_page_count, file_path)
    pages = []
    for page_no in range(1, count + 1):
        text = await asyncio.to_thread(_native_text, file_path, page_no)
        pages.append(SourcePage(page_no, "text" if len(text) >= settings.SOURCE_PAGE_MIN_TEXT_CHARS else "image", text))
    space = "multimodal" if any(page.modality == "image" for page in pages) else "text"
    vectors = [None] * len(pages)
    text_positions = [i for i, page in enumerate(pages) if page.modality == "text"]
    batch_size = 20 if space == "multimodal" else max(1, settings.EMBEDDING_MAX_BATCH_SIZE)
    for start in range(0, len(text_positions), batch_size):
        positions = text_positions[start:start + batch_size]
        if request_gate:
            await request_gate("source_page_text_embedding")
        embed = _dashscope_text_embeddings if space == "multimodal" else _openai_text_embeddings
        batch = await embed([pages[i].text for i in positions])
        for i, vector in zip(positions, batch):
            vectors[i] = vector
    # Render/send/discard one image at a time; never hold a whole scanned PDF as base64.
    for i, page in enumerate(pages):
        if page.modality == "image":
            if request_gate:
                await request_gate("source_page_image_embedding")
            image = await asyncio.to_thread(_render_page, file_path, page.page_no)
            vectors[i] = (await _dashscope_image_embeddings([image]))[0]
    _validated_vectors([{"index": i, "embedding": vector} for i, vector in enumerate(vectors)],
                       len(pages), len(vectors[0]) if vectors and vectors[0] else None, "source_index_invalid")
    return SourcePageIndex(source_hash, pages, vectors, _profile(space), space)


async def retrieve_source_pages(index: SourcePageIndex, queries: Dict[str, str], *, request_gate=None) -> Dict[str, List[SourcePageCandidate]]:
    """Batch field queries once per provider batch and rank top two physical pages."""
    result = {path: [] for path in queries}
    if not index.pages or not queries:
        return result
    if index.embedding_space not in ("text", "multimodal"):
        raise SourcePageIndexError("source_embedding_space_mismatch")
    if len({page.page_no for page in index.pages}) != len(index.pages):
        raise SourcePageIndexError("source_index_invalid", "duplicate physical pages")
    vectors = _validated_vectors([{"index": i, "embedding": vector} for i, vector in enumerate(index.vectors)],
                                 len(index.pages), None, "source_index_invalid")
    multimodal = index.embedding_space == "multimodal"
    embed = _dashscope_text_embeddings if multimodal else _openai_text_embeddings
    batch_size = 20 if multimodal else max(1, settings.EMBEDDING_MAX_BATCH_SIZE)
    items = [(path, query) for path, query in queries.items() if query.strip()]
    for start in range(0, len(items), batch_size):
        batch = items[start:start + batch_size]
        if request_gate:
            await request_gate("source_page_image_query_embedding" if multimodal else "source_page_text_query_embedding")
        query_vectors = await embed([query for _, query in batch])
        _validated_vectors([{"index": i, "embedding": vector} for i, vector in enumerate(query_vectors)],
                           len(batch), len(vectors[0]), "source_query_embedding_invalid")
        for (path, _), query_vector in zip(batch, query_vectors):
            ranked = sorted(zip(index.pages, vectors), key=lambda pair: (-_cosine(query_vector, pair[1]), pair[0].page_no))
            result[path] = [SourcePageCandidate(page.page_no, _cosine(query_vector, vector), [f"{page.modality}-vector"])
                            for page, vector in ranked[:2]]
    return result
