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
    # Preserve line boundaries for cheap heading/table detection.  Flattening
    # here made a page with "9.1.2 次要疗效指标" indistinguishable from body text.
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in output.splitlines()]
    return "\n".join(line for line in lines if line)


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
    source_hash = await asyncio.to_thread(_source_hash, file_path)
    count = await asyncio.to_thread(_page_count, file_path)
    pages = []
    for page_no in range(1, count + 1):
        text = await asyncio.to_thread(_native_text, file_path, page_no)
        pages.append(SourcePage(page_no, "text" if len(text) >= settings.SOURCE_PAGE_MIN_TEXT_CHARS else "image", text))
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
    # Render/send/discard one image at a time; never hold a whole scanned PDF as base64.
    for i, chunk in enumerate(chunks):
        if chunk.modality == "image":
            if request_gate:
                await request_gate("source_page_image_embedding")
            image = await asyncio.to_thread(_render_page, file_path, chunk.page_no)
            vectors[i] = (await _dashscope_image_embeddings([image]))[0]
    _validated_vectors([{"index": i, "embedding": vector} for i, vector in enumerate(vectors)],
                       len(chunks), len(vectors[0]) if vectors and vectors[0] else None, "source_index_invalid")
    return SourcePageIndex(source_hash, pages, vectors, _profile(space), chunks, space)


async def retrieve_source_pages(index: SourcePageIndex, queries: Dict[str, str], *, request_gate=None) -> Dict[str, List[SourcePageCandidate]]:
    """Batch field queries and rank logical chunks, returning physical pages.

    Lexical/structural evidence is fused with dense similarity.  The returned
    candidates remain page-shaped so the existing MinerU page-range boundary
    and evidence contract do not change.
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
    vectors = _validated_vectors([{"index": i, "embedding": vector} for i, vector in enumerate(index.vectors)],
                                 len(units), None, "source_index_invalid")
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
        for (path, query), query_vector in zip(batch, query_vectors):
            ranked = sorted(
                zip(units, vectors),
                key=lambda pair: (-_hybrid_score(pair[0], query, query_vector, pair[1]), pair[0].page_no, pair[0].chunk_id),
            )
            # Top-two remains the cheap baseline, but ranking now happens on
            # logical chunks.  Multiple chunks can map to one physical page.
            selected: Dict[int, SourcePageCandidate] = {}
            for unit, vector in ranked[:2]:
                lexical_score = _lexical_score(unit, query)
                score = _hybrid_score(unit, query, query_vector, vector)
                selected[unit.page_no] = SourcePageCandidate(
                    unit.page_no, score,
                    [f"{unit.modality}-vector", f"chunk:{unit.chunk_type}"]
                    + (["lexical"] if lexical_score else []),
                    ["embedding"] + (["lexical"] if lexical_score else []),
                )
            structural = _structural_candidates(units, query)
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
                        if neighbor_no < 1 or neighbor_no > len(index.pages):
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
            result[path] = sorted(selected.values(), key=lambda candidate: (-candidate.score, candidate.page_no))
    return result


def select_source_pages(candidates: Dict[str, List[SourcePageCandidate]], *, max_pages: int) -> tuple[list[int], dict[str, list[str]]]:
    """Merge and cap candidate pages without a document-specific rule.

    Structural and embedding hits outrank pure neighbor expansion; the latter
    only fills context when the cap leaves room.
    """
    by_page: dict[int, tuple[float, set[str]]] = {}
    for rows in candidates.values():
        for candidate in rows:
            sources = set(candidate.sources or candidate.reasons)
            bonus = 0.02 if "structural" in sources else 0.0
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


def _lexical_score(unit: SourceChunk, query: str) -> float:
    tokens = _query_tokens(query)
    if not tokens:
        return 0.0
    heading = " ".join(unit.heading_path).lower()
    body = (unit.text or "").lower()
    heading_hits = sum(token in heading for token in tokens)
    body_hits = sum(token in body for token in tokens)
    return min(1.0, 0.18 * heading_hits + 0.06 * body_hits)


def _hybrid_score(unit: SourceChunk, query: str, query_vector: Sequence[float], vector: Sequence[float]) -> float:
    dense = _cosine(query_vector, vector)
    lexical = _lexical_score(unit, query)
    return 0.68 * dense + 0.32 * lexical


def _structural_candidates(units: Sequence[SourceChunk], query: str) -> List[tuple[SourceChunk, float]]:
    """Find cheap heading/table matches from already-read page text.

    This is intentionally lexical and conservative: it only contributes pages
    with a positive overlap and never replaces embedding retrieval.
    """
    tokens = _query_tokens(query)
    if not tokens:
        return []
    matches: List[tuple[SourceChunk, float]] = []
    for unit in units:
        lines = [line.strip() for line in unit.text.splitlines() if line.strip()]
        headings = [line for line in lines if len(line) <= 160 and _HEADING_RE.search(line)]
        haystack = " ".join((*unit.heading_path, *(headings or lines[:3]))).lower()
        overlap = sum(1 for token in tokens if token in haystack)
        table_cue = sum(marker in unit.text for marker in ("|", "项目", "规格", "剂量", "用药"))
        if overlap or (table_cue >= 2 and any(token in unit.text for token in tokens)):
            matches.append((unit, min(0.99, 0.55 + 0.08 * overlap + 0.03 * table_cue)))
    return sorted(matches, key=lambda item: (-item[1], item[0].page_no, item[0].chunk_id))[:8]


def _needs_neighbor_expansion(query: str) -> bool:
    lowered = (query or "").lower()
    return any(marker in lowered for marker in (
        "列表", "逐条", "完整", "定义", "时间点", "表格", "产品", "标准", "criteria", "endpoint", "table"
    ))
