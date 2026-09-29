"""Build a per-Extract-Job retrieval index from the uploaded source file.

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
import re
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple

import httpx
import numpy as np
from loguru import logger

from config.settings import settings
from services import platform_model_client

# Hybrid-scoring weights. ADR-0011 keeps these in the generic router core for
# now; moving them into a strategy profile stays deferred until measurements
# justify it.
HYBRID_DENSE_WEIGHT = 0.68
HYBRID_LEXICAL_WEIGHT = 0.32
LEXICAL_HEADING_WEIGHT = 0.18
LEXICAL_BODY_WEIGHT = 0.06

# How many scanned pages may render ahead of their embedding request.
_IMAGE_RENDER_LOOKAHEAD = 3
_RENDER_OVERSIZE_DPI_SCALE = 0.75
_RENDER_MIN_DPI = 96

# Selection fusion: structural/lexical hits outrank pure neighbor expansion.
STRUCTURAL_PAGE_BONUS = 0.02
# Description-driven neighbor expansion heuristic (ADR-0011: generic markers,
# not field names).  Moving these into a strategy profile stays deferred.
NEIGHBOR_EXPANSION_MARKERS = (
    "列表", "逐条", "完整", "定义", "时间点", "表格", "产品", "标准", "criteria", "endpoint", "table",
)
# Generic table cues used by structural candidate scoring.
TABLE_CUE_MARKERS = ("|", "项目", "规格", "剂量", "用药")


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
class SourceChunk:
    """Job-local retrieval unit mapped back to one physical PDF page.

    A chunk is deliberately smaller than a ParseResult page when headings or
    tables make that boundary obvious.  MinerU still receives physical pages;
    this object only improves recall and keeps the source provenance attached.
    """

    chunk_id: str
    page_no: int
    modality: str
    text: str = ""
    chunk_type: str = "page"
    heading_path: Sequence[str] = ()
    parent_chunk_id: Optional[str] = None


@dataclass(frozen=True)
class SourcePageIndex:
    source_hash: str
    pages: Sequence[SourcePage]
    vectors: Sequence[Sequence[float]]
    profile: str
    chunks: Sequence[SourceChunk]
    embedding_space: str = "text"


@dataclass(frozen=True)
class SourcePageCandidate:
    page_no: int
    score: float
    reasons: Sequence[str]
    sources: Sequence[str] = ()


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


def _clean_page_text(output: str) -> str:
    # Preserve line boundaries for cheap heading/table detection.  Flattening
    # here made a page with "9.1.2 次要疗效指标" indistinguishable from body text.
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in output.splitlines()]
    return "\n".join(line for line in lines if line)


_WHOLE_DOC_TEXT_TIMEOUT_SECONDS = 120


def _native_pages_text(path: str, expected_count: int) -> Optional[List[str]]:
    """One whole-document pdftotext call split on form feeds; None on mismatch.

    pdftotext ends every page (including the last) with a form feed, so the
    split cardinality must match pdfinfo exactly; any disagreement returns
    None and the caller falls back to per-page reads instead of guessing the
    page mapping.
    """
    try:
        output = subprocess.check_output(
            ["pdftotext", "-layout", path, "-"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=_WHOLE_DOC_TEXT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SourcePageIndexError("source_text_read_failed", str(exc)) from exc
    parts = output.split("\f")
    if parts and not parts[-1].strip():
        parts.pop()
    if len(parts) != expected_count:
        return None
    return [_clean_page_text(part) for part in parts]


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
    return _clean_page_text(output)


def _render_page_png(path: str, page_no: int, dpi: int) -> bytes:
    with tempfile.TemporaryDirectory(prefix="neoflow-source-page-") as directory:
        prefix = str(Path(directory) / "page")
        subprocess.check_call(
            [
                "pdftoppm",
                "-f", str(page_no),
                "-l", str(page_no),
                "-png",
                "-singlefile",
                "-r", str(dpi),
                path,
                prefix,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
        )
        return Path(prefix + ".png").read_bytes()


def _render_page(path: str, page_no: int) -> str:
    cap = min(settings.SOURCE_PAGE_MAX_IMAGE_BYTES, 5 * 1024 * 1024)
    dpi = int(settings.SOURCE_PAGE_RENDER_DPI)
    try:
        data = _render_page_png(path, page_no, dpi)
        if len(data) > cap:
            # One lower-DPI retry before giving up: an oversized page used to
            # fail the whole Job at a fixed render resolution.
            retry_dpi = max(_RENDER_MIN_DPI, round(dpi * _RENDER_OVERSIZE_DPI_SCALE))
            data = _render_page_png(path, page_no, retry_dpi)
    except (OSError, subprocess.SubprocessError) as exc:
        raise SourcePageIndexError("source_image_render_failed", f"page={page_no}: {exc}") from exc
    if len(data) > cap or len(data) > settings.SOURCE_PAGE_MAX_IMAGE_BYTES:
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
    # Relay 模式：文本 Embedding 必须经平台 Relay（归因由平台注入）；
    # 本地 direct 模式才允许使用应用自配的 EMBEDDING_BASE_URL。
    if platform_model_client.model_access_mode() == "relay":
        try:
            return await platform_model_client.text_embeddings(
                inputs,
                model=settings.EMBEDDING_MODEL,
                dimensions=settings.EMBEDDING_DIMENSION or None,
            )
        except platform_model_client.PlatformModelError as exc:
            raise SourcePageIndexError(
                "source_text_embedding_unavailable", exc.reason
            ) from exc
    if not settings.EMBEDDING_API_KEY or not settings.EMBEDDING_BASE_URL:
        raise SourcePageIndexError("source_text_embedding_unavailable")
    payload = await _post(settings.EMBEDDING_BASE_URL.rstrip("/") + "/embeddings", settings.EMBEDDING_API_KEY, {
        "model": settings.EMBEDDING_MODEL, "input": list(inputs), "encoding_format": "float",
        **({"dimensions": settings.EMBEDDING_DIMENSION} if settings.EMBEDDING_DIMENSION else {}),
    }, "source_text_embedding")
    return _validated_vectors(payload.get("data"), len(inputs), settings.EMBEDDING_DIMENSION or None, "source_text_embedding_invalid")


async def _dashscope_embeddings(contents: Sequence[dict]) -> List[List[float]]:
    # P0：DashScope 多模态图片 Embedding 尚未接入 Relay（非 OpenAI 兼容格式）。
    # 平台 Relay 模式下明确失败，绝不静默直连外部 Provider。
    if platform_model_client.model_access_mode() == "relay":
        raise SourcePageIndexError(
            "source_image_model_capability_unavailable",
            "image embedding is not routed through the platform relay yet",
        )
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
    values = {"version": 3, "chunker": "heading-table-v1", "space": space, "min_text_chars": settings.SOURCE_PAGE_MIN_TEXT_CHARS,
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
    started = time.perf_counter()
    source_hash = await asyncio.to_thread(_source_hash, file_path)
    count = await asyncio.to_thread(_page_count, file_path)
    texts = await asyncio.to_thread(_native_pages_text, file_path, count)
    if texts is None:
        # Form-feed split disagreed with pdfinfo; per-page reads keep the page
        # mapping trustworthy at the cost of one subprocess per page.
        texts = [
            await asyncio.to_thread(_native_text, file_path, page_no)
            for page_no in range(1, count + 1)
        ]
    pages = [
        SourcePage(
            page_no,
            "text" if len(text) >= settings.SOURCE_PAGE_MIN_TEXT_CHARS else "image",
            text,
        )
        for page_no, text in enumerate(texts, start=1)
    ]
    chunks = _build_chunks(pages)
    space = "multimodal" if any(page.modality == "image" for page in pages) else "text"
    vectors = [None] * len(chunks)
    text_positions = [i for i, chunk in enumerate(chunks) if chunk.modality == "text"]
    batch_size = 20 if space == "multimodal" else max(1, settings.EMBEDDING_MAX_BATCH_SIZE)
    for start in range(0, len(text_positions), batch_size):
        positions = text_positions[start:start + batch_size]
        if request_gate:
            await request_gate("source_page_text_embedding")
        embed = _dashscope_text_embeddings if space == "multimodal" else _openai_text_embeddings
        batch = await embed([chunks[i].text for i in positions])
        for i, vector in zip(positions, batch):
            vectors[i] = vector
    # Render/send/discard one image at a time; never hold a whole scanned PDF
    # as base64.  Rendering runs a few pages ahead of the embedding requests
    # (bounded by _IMAGE_RENDER_LOOKAHEAD) so CPU rendering overlaps network
    # latency without pre-rendering the whole document.
    image_positions = [i for i, chunk in enumerate(chunks) if chunk.modality == "image"]
    pending: "deque[asyncio.Task]" = deque()
    scheduled = 0
    try:
        for position in image_positions[:_IMAGE_RENDER_LOOKAHEAD]:
            pending.append(
                asyncio.create_task(asyncio.to_thread(_render_page, file_path, chunks[position].page_no))
            )
            scheduled += 1
        for position in image_positions:
            if request_gate:
                await request_gate("source_page_image_embedding")
            image = await pending.popleft()
            if scheduled < len(image_positions):
                pending.append(
                    asyncio.create_task(asyncio.to_thread(_render_page, file_path, chunks[image_positions[scheduled]].page_no))
                )
                scheduled += 1
            vectors[position] = (await _dashscope_image_embeddings([image]))[0]
    finally:
        for task in pending:
            task.cancel()
    _validated_vectors([{"index": i, "embedding": vector} for i, vector in enumerate(vectors)],
                       len(chunks), len(vectors[0]) if vectors and vectors[0] else None, "source_index_invalid")
    logger.info(
        f"source-page index built: pages={len(pages)} chunks={len(chunks)} space={space} "
        f"elapsed_ms={int((time.perf_counter() - started) * 1000)}"
    )
    return SourcePageIndex(source_hash, pages, vectors, _profile(space), chunks, space)


def _normalized_vector_matrix(vectors: Sequence[Sequence[float]], *, reason: str) -> np.ndarray:
    """Validate once and return a row-normalized float64 matrix for scoring."""
    try:
        matrix = np.asarray(vectors, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise SourcePageIndexError(reason, "invalid vector") from exc
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise SourcePageIndexError(reason, "vector dimension")
    if not np.isfinite(matrix).all():
        raise SourcePageIndexError(reason, "non-finite or invalid vector")
    norms = np.linalg.norm(matrix, axis=1)
    if bool(np.any(norms == 0.0)):
        raise SourcePageIndexError(reason, "vector dimension or norm")
    return matrix / norms[:, None]


async def retrieve_source_pages(index: SourcePageIndex, queries: Dict[str, str], *, request_gate=None) -> Dict[str, List[SourcePageCandidate]]:
    """Batch field queries and rank logical chunks, returning physical pages.

    Lexical/structural evidence is fused with dense similarity.  The returned
    candidates remain page-shaped so the existing MinerU page-range boundary
    and evidence contract do not change.  Dense scoring runs as one normalized
    matrix product per batch in a worker thread so the event loop (and the
    worker heartbeat sharing it) is never blocked by chunk-scoring.
    """
    result = {path: [] for path in queries}
    if not index.pages or not queries:
        return result
    if index.embedding_space not in ("text", "multimodal"):
        raise SourcePageIndexError("source_embedding_space_mismatch")
    if len({page.page_no for page in index.pages}) != len(index.pages):
        raise SourcePageIndexError("source_index_invalid", "duplicate physical pages")
    if len(index.chunks) != len(index.vectors):
        raise SourcePageIndexError("source_index_invalid", "chunk/vector cardinality")
    units = list(index.chunks)
    if not units:
        return result
    matrix = await asyncio.to_thread(
        _normalized_vector_matrix, index.vectors, reason="source_index_invalid"
    )
    multimodal = index.embedding_space == "multimodal"
    embed = _dashscope_text_embeddings if multimodal else _openai_text_embeddings
    batch_size = 20 if multimodal else max(1, settings.EMBEDDING_MAX_BATCH_SIZE)
    items = [(path, query) for path, query in queries.items() if query.strip()]
    page_count = len(index.pages)
    started = time.perf_counter()
    for start in range(0, len(items), batch_size):
        batch = items[start:start + batch_size]
        if request_gate:
            await request_gate("source_page_image_query_embedding" if multimodal else "source_page_text_query_embedding")
        query_vectors = await embed([query for _, query in batch])
        _validated_vectors([{"index": i, "embedding": vector} for i, vector in enumerate(query_vectors)],
                           len(batch), matrix.shape[1], "source_query_embedding_invalid")
        query_matrix = await asyncio.to_thread(
            _normalized_vector_matrix, query_vectors, reason="source_query_embedding_invalid"
        )
        if query_matrix.shape[1] != matrix.shape[1]:
            raise SourcePageIndexError("source_embedding_space_mismatch")
        ranked = await asyncio.to_thread(
            _rank_query_batch, units, matrix, batch, query_matrix, page_count
        )
        result.update(ranked)
    logger.info(
        f"source-page retrieve: chunks={len(units)} queries={len(items)} "
        f"elapsed_ms={int((time.perf_counter() - started) * 1000)}"
    )
    return result


def _rank_query_batch(
    units: Sequence[SourceChunk],
    matrix: np.ndarray,
    batch: Sequence[Tuple[str, str]],
    query_matrix: np.ndarray,
    page_count: int,
) -> Dict[str, List[SourcePageCandidate]]:
    """Pure-CPU hybrid ranking for one embedding batch (runs in a worker thread)."""
    top_k = max(1, int(settings.SOURCE_PAGE_TOP_K_PER_FIELD))
    ranked_by_path: Dict[str, List[SourcePageCandidate]] = {}
    for row, ((path, query), _) in enumerate(zip(batch, query_matrix)):
        query_vector = query_matrix[row]
        tokens = _query_tokens(query)
        dense = matrix @ query_vector
        lexical = [_lexical_score_tokens(unit, tokens) for unit in units]
        hybrid = [
            HYBRID_DENSE_WEIGHT * float(dense[i]) + HYBRID_LEXICAL_WEIGHT * lexical[i]
            for i in range(len(units))
        ]
        # Top-K remains the cheap baseline, but ranking now happens on
        # logical chunks.  Multiple chunks can map to one physical page.
        order = sorted(
            range(len(units)),
            key=lambda i: (-hybrid[i], units[i].page_no, units[i].chunk_id),
        )
        selected: Dict[int, SourcePageCandidate] = {}
        for i in order[:top_k]:
            unit = units[i]
            selected[unit.page_no] = SourcePageCandidate(
                unit.page_no, hybrid[i],
                [f"{unit.modality}-vector", f"chunk:{unit.chunk_type}"]
                + (["lexical"] if lexical[i] else []),
                ["embedding"] + (["lexical"] if lexical[i] else []),
            )
        structural = _structural_candidates(units, tokens)
        for unit, score in structural:
            existing = selected.get(unit.page_no)
            if existing:
                selected[unit.page_no] = SourcePageCandidate(
                    existing.page_no, max(existing.score, score),
                    list(dict.fromkeys([*existing.reasons, "structural"])),
                    list(dict.fromkeys([*existing.sources, "structural"])),
                )
            else:
                selected[unit.page_no] = SourcePageCandidate(
                    unit.page_no, score, ["structural", f"chunk:{unit.chunk_type}"], ["structural"]
                )
        if _needs_neighbor_expansion(query):
            base_pages = list(selected)
            for page_no in base_pages:
                for neighbor_no in (page_no - 1, page_no + 1):
                    if neighbor_no < 1 or neighbor_no > page_count:
                        continue
                    if neighbor_no not in selected:
                        selected[neighbor_no] = SourcePageCandidate(
                            neighbor_no, 0.0, ["neighbor"], ["neighbor"]
                        )
                    else:
                        current = selected[neighbor_no]
                        selected[neighbor_no] = SourcePageCandidate(
                            current.page_no, current.score,
                            list(dict.fromkeys([*current.reasons, "neighbor"])),
                            list(dict.fromkeys([*current.sources, "neighbor"])),
                        )
        ranked_by_path[path] = sorted(selected.values(), key=lambda candidate: (-candidate.score, candidate.page_no))
    return ranked_by_path


def select_source_pages(candidates: Dict[str, List[SourcePageCandidate]], *, max_pages: int) -> tuple[list[int], dict[str, list[str]]]:
    """Merge and cap candidate pages without a document-specific rule.

    Structural and embedding hits outrank pure neighbor expansion; the latter
    only fills context when the cap leaves room.
    """
    by_page: dict[int, tuple[float, set[str]]] = {}
    for rows in candidates.values():
        for candidate in rows:
            sources = set(candidate.sources or candidate.reasons)
            bonus = STRUCTURAL_PAGE_BONUS if "structural" in sources else 0.0
            score = float(candidate.score) + bonus
            current = by_page.get(candidate.page_no)
            if current is None or score > current[0]:
                by_page[candidate.page_no] = (score, sources)
            elif score == current[0]:
                by_page[candidate.page_no] = (score, current[1] | sources)
    ranked = sorted(by_page.items(), key=lambda item: (-item[1][0], item[0]))
    selected = sorted(page for page, _ in ranked[:max(1, int(max_pages))])
    source_map = {str(page): sorted(by_page[page][1]) for page in selected}
    return selected, source_map


_STRUCTURAL_TOKEN_RE = re.compile(r"[A-Za-z0-9]{2,}|[\u4e00-\u9fff]{2,}")
_HEADING_RE = re.compile(
    r"^\s*(?:第\s*[一二三四五六七八九十百0-9]+[章节部分]|"
    r"[0-9]{1,3}(?:\.[0-9]+){0,3}(?:[、.]|\s+))"
)


def _query_tokens(value: str) -> set[str]:
    return {token.lower() for token in _STRUCTURAL_TOKEN_RE.findall(value or "") if len(token) >= 2}


def _is_heading(line: str) -> bool:
    return bool(_HEADING_RE.search(line))


def _build_chunks(pages: Sequence[SourcePage]) -> List[SourceChunk]:
    """Split only where the source exposes a heading; otherwise keep one page chunk."""
    chunks: List[SourceChunk] = []
    for page in pages:
        if page.modality != "text" or not page.text.strip():
            chunks.append(SourceChunk(f"p{page.page_no}-c0", page.page_no, page.modality, page.text, "page"))
            continue
        lines = [line.strip() for line in page.text.splitlines() if line.strip()]
        if not lines:
            chunks.append(SourceChunk(f"p{page.page_no}-c0", page.page_no, page.modality, "", "page"))
            continue
        parts: List[List[str]] = []
        current: List[str] = []
        for line in lines:
            if current and _is_heading(line):
                parts.append(current)
                current = []
            current.append(line)
        if current:
            parts.append(current)
        if len(parts) == 1:
            chunks.append(SourceChunk(f"p{page.page_no}-c0", page.page_no, page.modality,
                                       "\n".join(parts[0]), "page"))
            continue
        for offset, lines_for_chunk in enumerate(parts):
            text = "\n".join(lines_for_chunk)
            heading = lines_for_chunk[0] if _is_heading(lines_for_chunk[0]) else ""
            chunk_type = "table" if ("|" in text or sum(marker in text for marker in ("规格", "剂量", "生产单位")) >= 2) else "section"
            chunks.append(SourceChunk(
                f"p{page.page_no}-c{offset}", page.page_no, page.modality, text,
                chunk_type, (heading,) if heading else (), f"p{page.page_no}",
            ))
    return chunks


def _lexical_score_tokens(unit: SourceChunk, tokens: set[str]) -> float:
    if not tokens:
        return 0.0
    heading = " ".join(unit.heading_path).lower()
    body = (unit.text or "").lower()
    heading_hits = sum(token in heading for token in tokens)
    body_hits = sum(token in body for token in tokens)
    return min(1.0, LEXICAL_HEADING_WEIGHT * heading_hits + LEXICAL_BODY_WEIGHT * body_hits)


def _structural_candidates(units: Sequence[SourceChunk], tokens: set[str]) -> List[tuple[SourceChunk, float]]:
    """Find cheap heading/table matches from already-read page text.

    This is intentionally lexical and conservative: it only contributes pages
    with a positive overlap and never replaces embedding retrieval.
    """
    if not tokens:
        return []
    matches: List[tuple[SourceChunk, float]] = []
    for unit in units:
        lines = [line.strip() for line in unit.text.splitlines() if line.strip()]
        headings = [line for line in lines if len(line) <= 160 and _HEADING_RE.search(line)]
        haystack = " ".join((*unit.heading_path, *(headings or lines[:3]))).lower()
        overlap = sum(1 for token in tokens if token in haystack)
        table_cue = sum(marker in unit.text for marker in TABLE_CUE_MARKERS)
        if overlap or (table_cue >= 2 and any(token in unit.text for token in tokens)):
            matches.append((unit, min(0.99, 0.55 + 0.08 * overlap + 0.03 * table_cue)))
    return sorted(matches, key=lambda item: (-item[1], item[0].page_no, item[0].chunk_id))[:8]


def _needs_neighbor_expansion(query: str) -> bool:
    lowered = (query or "").lower()
    return any(marker in lowered for marker in NEIGHBOR_EXPANSION_MARKERS)
