"""Document Page Index for the optional page-routed Extract strategy.

The first slice is deliberately small:
- the input is one already-bound, complete ParseResult;
- one embedding represents one physical page;
- vector and lexical candidates are unioned before neighbor expansion;
- the index is a derived cache, never a ParseResult or an Extraction Result.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Protocol, Sequence

import httpx

from config.settings import settings
from services.base import SupabaseClientMixin

PAGE_STATES = ("parsed", "blank", "parse_failed", "unknown", "unencoded")
_TERM_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9][A-Za-z0-9_.+\-/]*")


class PageIndexError(Exception):
    """A typed Page Index failure; callers must not turn it into document absence."""

    def __init__(self, reason: str, message: str = ""):
        super().__init__(f"{reason}: {message}" if message else reason)
        self.reason = reason
        self.message = message


@dataclass(frozen=True)
class EmbeddingProfile:
    model: str
    dimension: Optional[int] = None
    query_instruction: str = ""
    document_instruction: str = ""
    normalize: bool = True
    version: str = "v1"

    @property
    def identity(self) -> str:
        payload = {
            "model": self.model,
            "dimension": self.dimension,
            "query_instruction": self.query_instruction,
            "document_instruction": self.document_instruction,
            "normalize": self.normalize,
            "version": self.version,
        }
        return stable_hash(payload)


@dataclass
class PageIndexPage:
    page_no: int
    state: str
    text: str
    text_hash: Optional[str]
    source: Optional[str]
    embedding: Optional[List[float]] = None
    embedding_profile_hash: Optional[str] = None
    error: Optional[str] = None


@dataclass
class PageCandidate:
    page_no: int
    score: float
    reasons: List[str] = field(default_factory=list)


@dataclass
class PageIndexSnapshot:
    tenant_id: str
    document_id: str
    parse_result_id: str
    source_document_hash: str
    text_profile_hash: str
    embedding_profile_hash: str
    pages: List[PageIndexPage]


class EmbeddingProvider(Protocol):
    async def embed_documents(
        self, texts: Sequence[str], profile: EmbeddingProfile
    ) -> List[List[float]]:
        ...

    async def embed_query(self, text: str, profile: EmbeddingProfile) -> List[float]:
        ...


class OpenAICompatibleEmbeddingProvider:
    """Small OpenAI-compatible adapter; no vector database dependency."""

    async def _request(
        self, inputs: Sequence[str] | str, profile: EmbeddingProfile
    ) -> List[List[float]]:
        if not settings.EMBEDDING_API_KEY or not settings.EMBEDDING_BASE_URL:
            raise PageIndexError("embedding_unavailable", "embedding provider is not configured")
        if profile.query_instruction or profile.document_instruction:
            # DashScope instruct/text_type require its native API, not /embeddings.
            raise PageIndexError("embedding_profile_unsupported", "instructions require a supporting adapter")
        try:
            async with httpx.AsyncClient(timeout=settings.EMBEDDING_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{settings.EMBEDDING_BASE_URL.rstrip('/')}/embeddings",
                    headers={
                        "Authorization": f"Bearer {settings.EMBEDDING_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": profile.model,
                        "input": inputs,
                        "encoding_format": "float",
                        **({"dimensions": profile.dimension} if profile.dimension else {}),
                    },
                )
        except httpx.HTTPError as exc:
            raise PageIndexError("embedding_provider_failed", type(exc).__name__) from exc
        if response.status_code >= 400:
            raise PageIndexError("embedding_provider_failed", f"HTTP {response.status_code}")
        try:
            payload = response.json()
            rows = payload["data"]
            expected_count = 1 if isinstance(inputs, str) else len(inputs)
            if not isinstance(rows, list) or len(rows) != expected_count:
                raise ValueError("batch cardinality mismatch")
            indices = [row["index"] for row in rows]
            if any(type(index) is not int for index in indices) or sorted(indices) != list(range(expected_count)):
                raise ValueError("batch index mismatch")
            rows = sorted(rows, key=lambda item: item["index"])
            vectors = [row["embedding"] for row in rows]
        except (KeyError, TypeError, ValueError) as exc:
            raise PageIndexError("embedding_response_invalid", "invalid batch mapping") from exc
        return validate_vectors(vectors, profile)

    async def embed_documents(
        self, texts: Sequence[str], profile: EmbeddingProfile
    ) -> List[List[float]]:
        return await self._request(texts, profile)

    async def embed_query(self, text: str, profile: EmbeddingProfile) -> List[float]:
        rows = await self._request(text, profile)
        if len(rows) != 1:
            raise PageIndexError("embedding_response_invalid", "query response cardinality")
        return rows[0]


class PageEmbeddingStore(Protocol):
    async def list_rows(self, identity: Dict[str, str]) -> List[Dict[str, Any]]:
        ...

    async def upsert_rows(self, rows: Sequence[Dict[str, Any]]) -> None:
        ...


class InMemoryPageEmbeddingStore:
    """Test/local store. Production uses SupabasePageEmbeddingStore."""

    def __init__(self):
        self.rows: Dict[tuple, Dict[str, Any]] = {}

    async def list_rows(self, identity: Dict[str, str]) -> List[Dict[str, Any]]:
        return [
            dict(row)
            for row in self.rows.values()
            if all(row.get(key) == value for key, value in identity.items())
        ]

    async def upsert_rows(self, rows: Sequence[Dict[str, Any]]) -> None:
        for row in rows:
            key = tuple(row.get(name) for name in (
                "tenant_id", "document_id", "parse_result_id", "source_document_hash",
                "physical_page_no", "text_profile_hash", "embedding_profile_hash",
            ))
            self.rows[key] = dict(row)


class SupabasePageEmbeddingStore(SupabaseClientMixin):
    """Service-role persistence for the derived page-vector cache."""

    table_name = "document_page_embeddings"

    async def list_rows(self, identity: Dict[str, str]) -> List[Dict[str, Any]]:
        def query():
            request = self._get_client().table(self.table_name).select("*")
            for key, value in identity.items():
                request = request.eq(key, value)
            return request.execute()

        result = await self._run_sync(query)
        return result.data or []

    async def upsert_rows(self, rows: Sequence[Dict[str, Any]]) -> None:
        if not rows:
            return
        await self._run_sync(
            lambda: self._get_client().table(self.table_name).upsert(
                list(rows),
                on_conflict=(
                    "tenant_id,document_id,parse_result_id,source_document_hash,"
                    "physical_page_no,text_profile_hash,embedding_profile_hash"
                ),
            ).execute()
        )


def stable_hash(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def html_to_text(value: Any) -> str:
    raw = str(value or "")
    return normalize_text(html.unescape(re.sub(r"<[^>]+>", " ", raw)))


def page_text(page: Dict[str, Any]) -> str:
    markdown = normalize_text(page.get("markdown"))
    parts: List[str] = [markdown] if markdown else []
    for block in sorted(page.get("blocks") or [], key=lambda item: item.get("reading_order", 0)):
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        values: List[str] = []
        text = normalize_text(block.get("text"))
        table = html_to_text(block.get("table_html"))
        latex = normalize_text(block.get("latex"))
        if text and text not in parts and text not in markdown:
            values.append(text)
        if table and (block_type == "table" or table != text) and table not in markdown:
            values.append(table)
        if latex and latex not in values and latex not in markdown:
            values.append(latex)
        parts.extend(values)
    return "\n".join(parts).strip()


def lexical_terms(value: str) -> List[str]:
    return [term.casefold() for term in _TERM_RE.findall(value or "") if len(term) > 1]


def lexical_score(query: str, text: str) -> float:
    terms = lexical_terms(query)
    if not terms:
        return 0.0
    haystack = (text or "").casefold()
    hits = sum(1 for term in terms if term in haystack)
    return hits / len(set(terms))


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def validate_vectors(vectors: Sequence[Sequence[float]], profile: EmbeddingProfile) -> List[List[float]]:
    if not isinstance(vectors, (list, tuple)):
        raise PageIndexError("embedding_response_invalid", "vectors must be a list")
    normalized: List[List[float]] = []
    dimension: Optional[int] = None
    for vector in vectors:
        if not isinstance(vector, (list, tuple)) or not vector:
            raise PageIndexError("embedding_response_invalid", "empty vector")
        if any(type(value) not in (int, float) for value in vector):
            raise PageIndexError("embedding_response_invalid", "non-numeric vector")
        try:
            values = [float(value) for value in vector]
            norm = math.hypot(*values)
        except (ValueError, OverflowError) as exc:
            raise PageIndexError("embedding_response_invalid", "invalid vector magnitude") from exc
        if not math.isfinite(norm) or norm == 0:
            raise PageIndexError("embedding_response_invalid", "non-finite or zero vector")
        dimension = dimension or len(values)
        if len(values) != dimension:
            raise PageIndexError("embedding_response_invalid", "dimension mismatch")
        if profile.dimension and len(values) != profile.dimension:
            raise PageIndexError("embedding_response_invalid", "unexpected dimension")
        if profile.normalize:
            values = [value / norm for value in values]
        normalized.append(values)
    return normalized


class PageIndexService:
    def __init__(
        self,
        *,
        store: Optional[PageEmbeddingStore] = None,
        provider: Optional[EmbeddingProvider] = None,
    ):
        self.store = store or SupabasePageEmbeddingStore()
        self.provider = provider or OpenAICompatibleEmbeddingProvider()

    @staticmethod
    def _coverage(parse_row: Dict[str, Any]) -> Dict[str, Any]:
        data = parse_row.get("data") or {}
        engine = data.get("engine") if isinstance(data, dict) else None
        coverage = engine.get("coverage") if isinstance(engine, dict) else None
        if not isinstance(coverage, dict):
            raise PageIndexError("parse_coverage_unknown", "ParseResult coverage is not recorded")
        status = coverage.get("status")
        if status != "complete":
            reason = "parse_coverage_incomplete" if status in ("partial", "incomplete") else "parse_coverage_unknown"
            raise PageIndexError(reason, str(coverage.get("reason") or status))
        expected = coverage.get("expected_page_count")
        observed = sorted(int(page) for page in coverage.get("observed_page_numbers") or [])
        if not isinstance(expected, int) or expected <= 0 or observed != list(range(1, expected + 1)):
            raise PageIndexError("parse_coverage_incomplete", "physical page coverage is not contiguous")
        return coverage

    @staticmethod
    def _page_records(parse_row: Dict[str, Any]) -> List[PageIndexPage]:
        data = parse_row.get("data") or {}
        records: List[PageIndexPage] = []
        for raw_page in data.get("pages") or []:
            try:
                page_no = int(raw_page.get("page_no"))
            except (TypeError, ValueError):
                raise PageIndexError("page_identity_invalid", "page_no is not an integer")
            text = page_text(raw_page)
            state = "parsed" if text else "blank"
            sources = {
                str(block.get("source"))
                for block in (raw_page.get("blocks") or [])
                if block.get("source")
            }
            records.append(PageIndexPage(
                page_no=page_no,
                state=state,
                text=text,
                text_hash=stable_hash(text) if text else None,
                source=(next(iter(sources)) if len(sources) == 1 else "mixed" if sources else None),
            ))
        if not records:
            raise PageIndexError("parse_coverage_incomplete", "ParseResult has no pages")
        return sorted(records, key=lambda page: page.page_no)

    async def ensure_index(
        self,
        parse_row: Dict[str, Any],
        *,
        tenant_id: str,
        document_id: str,
        embedding_profile: EmbeddingProfile,
        text_profile_hash: Optional[str] = None,
        request_gate: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> PageIndexSnapshot:
        if str(parse_row.get("tenant_id") or "") != str(tenant_id):
            raise PageIndexError("tenant_mismatch", "ParseResult tenant does not match request")
        if str(parse_row.get("document_id") or "") != str(document_id):
            raise PageIndexError("document_mismatch", "ParseResult document does not match request")
        if parse_row.get("sample_key") != "parse":
            raise PageIndexError("parse_identity_invalid", "Page Index input is not a ParseResult")
        self._coverage(parse_row)
        parse_result_id = str(parse_row.get("id") or "")
        if not parse_result_id:
            raise PageIndexError("parse_identity_missing", "ParseResult id is required")
        data = parse_row.get("data") or {}
        engine = data.get("engine") or {}
        source_hash = engine.get("source_document_hash")
        if not source_hash:
            raise PageIndexError("source_identity_missing", "source_document_hash is required")
        text_profile_hash = text_profile_hash or engine.get("parse_profile_hash")
        if not text_profile_hash:
            raise PageIndexError("text_profile_missing", "parse_profile_hash is required")

        pages = self._page_records(parse_row)
        if len({page.page_no for page in pages}) != len(pages):
            raise PageIndexError("page_identity_invalid", "duplicate physical page number")
        identity = {
            "tenant_id": tenant_id,
            "document_id": document_id,
            "parse_result_id": parse_result_id,
            "source_document_hash": source_hash,
            "text_profile_hash": text_profile_hash,
            "embedding_profile_hash": embedding_profile.identity,
        }
        cached = await self.store.list_rows(identity)
        cached_by_page = {int(row["physical_page_no"]): row for row in cached}
        missing: List[PageIndexPage] = []
        state_rows: List[Dict[str, Any]] = []
        for page in pages:
            row = cached_by_page.get(page.page_no)
            if page.state != "parsed":
                page.source = row.get("page_source") if row else None
                if not row:
                    state_rows.append({
                        **identity,
                        "physical_page_no": page.page_no,
                        "page_state": page.state,
                        "page_source": page.source,
                        "page_text": page.text or None,
                        "page_text_hash": page.text_hash,
                        "embedding": None,
                        "embedding_dimension": None,
                        "error": page.error,
                    })
                continue
            if row and row.get("page_state") == "parsed" and row.get("page_text_hash") == page.text_hash:
                vector = row.get("embedding")
                try:
                    page.embedding = validate_vectors([vector], embedding_profile)[0]
                    page.embedding_profile_hash = embedding_profile.identity
                    page.source = row.get("page_source")
                    continue
                except (PageIndexError, TypeError, ValueError):
                    pass
            missing.append(page)

        if missing:
            batch_size = max(1, int(getattr(settings, "EMBEDDING_MAX_BATCH_SIZE", 20)))
            vectors: List[List[float]] = []
            for start in range(0, len(missing), batch_size):
                batch = missing[start : start + batch_size]
                if request_gate:
                    await request_gate("page_embeddings")
                batch_vectors = await self.provider.embed_documents(
                    [page.text for page in batch], embedding_profile
                )
                if len(batch_vectors) != len(batch):
                    raise PageIndexError("embedding_response_invalid", "batch cardinality mismatch")
                vectors.extend(validate_vectors(batch_vectors, embedding_profile))
            vectors = validate_vectors(vectors, embedding_profile)
            for page, vector in zip(missing, vectors):
                page.embedding = vector
                page.embedding_profile_hash = embedding_profile.identity
            await self.store.upsert_rows(state_rows + [
                {
                    **identity,
                    "physical_page_no": page.page_no,
                    "page_state": page.state,
                    "page_source": page.source,
                    "page_text": page.text,
                    "page_text_hash": page.text_hash,
                    "embedding": page.embedding,
                    "embedding_dimension": len(page.embedding or []),
                    "error": page.error,
                }
                for page in missing
            ])
        return PageIndexSnapshot(
            tenant_id=tenant_id,
            document_id=document_id,
            parse_result_id=parse_result_id,
            source_document_hash=source_hash,
            text_profile_hash=text_profile_hash,
            embedding_profile_hash=embedding_profile.identity,
            pages=pages,
        )

    async def retrieve(
        self,
        snapshot: PageIndexSnapshot,
        *,
        query: str,
        embedding_profile: Optional[EmbeddingProfile] = None,
        top_k: int = 5,
        neighbor_pages: int = 1,
        max_pages: int = 20,
        request_gate: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> List[PageCandidate]:
        profile = embedding_profile or EmbeddingProfile(
            model=settings.EMBEDDING_MODEL,
            dimension=settings.EMBEDDING_DIMENSION or None,
            query_instruction=settings.EMBEDDING_QUERY_INSTRUCTION,
            document_instruction=settings.EMBEDDING_DOCUMENT_INSTRUCTION,
            normalize=settings.EMBEDDING_NORMALIZE,
            version=settings.EMBEDDING_PROFILE_VERSION,
        )
        if request_gate:
            await request_gate("query_embedding")
        query_vector = await self.provider.embed_query(query, profile)
        query_vector = validate_vectors([query_vector], profile)[0]
        usable = [page for page in snapshot.pages if page.state == "parsed" and page.embedding]
        vector_rows = sorted(
            ((cosine_similarity(query_vector, page.embedding or []), page) for page in usable),
            key=lambda item: (-item[0], item[1].page_no),
        )[: max(0, top_k)]
        candidates: Dict[int, PageCandidate] = {}
        for score, page in vector_rows:
            candidates[page.page_no] = PageCandidate(page.page_no, score, ["vector"])
        lexical_rows = sorted(
            ((lexical_score(query, page.text), page) for page in usable),
            key=lambda item: (-item[0], item[1].page_no),
        )
        for score, page in lexical_rows[: max(0, top_k)]:
            if score <= 0:
                continue
            current = candidates.get(page.page_no)
            if current:
                current.reasons.append("lexical")
                current.score = max(current.score, score)
            else:
                candidates[page.page_no] = PageCandidate(page.page_no, score, ["lexical"])
        page_map = {page.page_no: page for page in snapshot.pages}
        base_pages = list(candidates)
        for page_no in base_pages:
            for offset in range(1, max(0, neighbor_pages) + 1):
                for neighbor in (page_no - offset, page_no + offset):
                    if neighbor in page_map and neighbor not in candidates:
                        candidates[neighbor] = PageCandidate(neighbor, 0.0, ["neighbor"])
        ordered = sorted(candidates.values(), key=lambda item: (-item.score, item.page_no))
        return ordered[: max(0, max_pages)]
