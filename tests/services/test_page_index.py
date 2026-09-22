import json

import httpx
import pytest

from services.page_index import (
    EmbeddingProfile,
    InMemoryPageEmbeddingStore,
    OpenAICompatibleEmbeddingProvider,
    PageIndexError,
    PageIndexService,
    page_text,
    validate_vectors,
)


TENANT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
DOCUMENT_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
PARSE_ID = "99999999-9999-4999-8999-999999999999"


class FakeEmbeddingProvider:
    def __init__(self):
        self.document_calls = []
        self.query_calls = []

    async def embed_documents(self, texts, profile):
        self.document_calls.append(list(texts))
        return [[1.0, 0.0] if "摘要" in text else [0.0, 1.0] for text in texts]

    async def embed_query(self, text, profile):
        self.query_calls.append(text)
        return [1.0, 0.0]


def _row(*pages, status="complete"):
    return {
        "id": PARSE_ID,
        "tenant_id": TENANT_ID,
        "document_id": DOCUMENT_ID,
        "sample_key": "parse",
        "data": {
            "engine": {
                "source_document_hash": "source-1",
                "parse_profile_hash": "text-profile-1",
                "coverage": {
                    "status": status,
                    "expected_page_count": 3,
                    "observed_page_numbers": [1, 2, 3],
                },
            },
            "pages": list(pages),
        },
    }


def _page(page_no, text, *, markdown=None, blocks=None):
    return {
        "page_no": page_no,
        "markdown": text if markdown is None else markdown,
        "blocks": blocks or [],
    }


@pytest.mark.asyncio
async def test_builds_and_reuses_one_vector_per_physical_page():
    provider = FakeEmbeddingProvider()
    store = InMemoryPageEmbeddingStore()
    service = PageIndexService(store=store, provider=provider)
    profile = EmbeddingProfile(model="fake", version="test")
    row = _row(_page(1, "摘要信息"), _page(2, "联系方式"), _page(3, "正文"))

    first = await service.ensure_index(
        row, tenant_id=TENANT_ID, document_id=DOCUMENT_ID, embedding_profile=profile
    )
    second = await service.ensure_index(
        row, tenant_id=TENANT_ID, document_id=DOCUMENT_ID, embedding_profile=profile
    )

    assert [page.page_no for page in first.pages] == [1, 2, 3]
    assert [page.page_no for page in second.pages] == [1, 2, 3]
    assert len(provider.document_calls) == 1
    assert len(store.rows) == 3


@pytest.mark.asyncio
async def test_splits_page_embeddings_into_provider_sized_batches(monkeypatch):
    provider = FakeEmbeddingProvider()
    service = PageIndexService(store=InMemoryPageEmbeddingStore(), provider=provider)
    profile = EmbeddingProfile(model="fake", version="test")
    monkeypatch.setattr("services.page_index.settings.EMBEDDING_MAX_BATCH_SIZE", 2)
    requests = []

    async def gate(stage):
        requests.append(stage)

    await service.ensure_index(
        _row(_page(1, "摘要"), _page(2, "正文"), _page(3, "正文")),
        tenant_id=TENANT_ID,
        document_id=DOCUMENT_ID,
        embedding_profile=profile,
        request_gate=gate,
    )

    assert [len(batch) for batch in provider.document_calls] == [2, 1]
    assert requests == ["page_embeddings", "page_embeddings"]


@pytest.mark.asyncio
async def test_http_provider_maps_shuffled_items_and_rejects_duplicate_indices(monkeypatch):
    from services.page_index import settings

    monkeypatch.setattr(settings, "EMBEDDING_API_KEY", "test-key")
    monkeypatch.setattr(settings, "EMBEDDING_BASE_URL", "https://embedding.example/v1")
    duplicate = False

    def respond(request):
        payload = json.loads(request.content)
        assert payload["dimensions"] == 2
        assert payload["encoding_format"] == "float"
        return httpx.Response(200, json={"data": [
            {"index": 0 if duplicate else 1, "embedding": [0.0, 1.0]},
            {"index": 0, "embedding": [1.0, 0.0]},
        ]})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(respond), **kwargs
    ))
    provider = OpenAICompatibleEmbeddingProvider()
    profile = EmbeddingProfile(model="test", dimension=2)
    assert await provider.embed_documents(["page one", "page two"], profile) == [[1.0, 0.0], [0.0, 1.0]]
    duplicate = True
    with pytest.raises(PageIndexError, match="embedding_response_invalid"):
        await provider.embed_documents(["page one", "page two"], profile)
    with pytest.raises(PageIndexError, match="embedding_profile_unsupported"):
        await provider.embed_query("query", EmbeddingProfile(model="test", query_instruction="retrieve"))


@pytest.mark.parametrize("vectors", [
    [[0.0, 0.0]], [[True, 1.0]], [["invalid", 1.0]],
    [[float("nan"), 1.0]], [[float("inf"), 1.0]], [[1.0, 0.0], [1.0]],
])
def test_invalid_vectors_cannot_enter_cache(vectors):
    with pytest.raises(PageIndexError, match="embedding_response_invalid"):
        validate_vectors(vectors, EmbeddingProfile(model="test"))


@pytest.mark.asyncio
async def test_vector_and_lexical_candidates_are_unioned_and_neighbors_added():
    provider = FakeEmbeddingProvider()
    service = PageIndexService(store=InMemoryPageEmbeddingStore(), provider=provider)
    profile = EmbeddingProfile(model="fake", version="test")
    row = _row(
        _page(1, "方案摘要"),
        _page(2, "负责人联系方式 手机号 13800138000"),
        _page(3, "正文"),
    )
    snapshot = await service.ensure_index(
        row, tenant_id=TENANT_ID, document_id=DOCUMENT_ID, embedding_profile=profile
    )

    candidates = await service.retrieve(
        snapshot,
        query="负责人联系方式 手机号",
        embedding_profile=profile,
        top_k=1,
        neighbor_pages=1,
        max_pages=5,
    )

    assert [candidate.page_no for candidate in candidates] == [1, 2, 3]
    assert "lexical" in candidates[1].reasons
    assert "neighbor" in candidates[0].reasons or "neighbor" in candidates[2].reasons


@pytest.mark.asyncio
async def test_embedding_and_query_requests_use_the_supplied_budget_gate():
    provider = FakeEmbeddingProvider()
    service = PageIndexService(store=InMemoryPageEmbeddingStore(), provider=provider)
    profile = EmbeddingProfile(model="fake", version="test")
    calls = []

    async def gate(stage):
        calls.append(stage)

    snapshot = await service.ensure_index(
        _row(_page(1, "摘要"), _page(2, "正文"), _page(3, "正文")),
        tenant_id=TENANT_ID,
        document_id=DOCUMENT_ID,
        embedding_profile=profile,
        request_gate=gate,
    )
    await service.retrieve(
        snapshot,
        query="摘要",
        embedding_profile=profile,
        request_gate=gate,
        top_k=1,
    )

    assert calls == ["page_embeddings", "query_embedding"]


def test_page_text_keeps_table_caption_body_and_footnote():
    text = page_text({
        "page_no": 1,
        "markdown": "",
        "blocks": [{
            "type": "table",
            "reading_order": 1,
            "text": "联系方式表",
            "table_html": "<table><tr><td>负责人</td><td>13800138000</td></tr></table>",
            "latex": None,
        }],
    })

    assert "联系方式表" in text
    assert "负责人" in text
    assert "13800138000" in text


@pytest.mark.asyncio
async def test_unknown_or_partial_coverage_fails_before_embedding():
    provider = FakeEmbeddingProvider()
    service = PageIndexService(store=InMemoryPageEmbeddingStore(), provider=provider)
    profile = EmbeddingProfile(model="fake", version="test")
    row = _row(_page(1, "摘要"), _page(2, "正文"), _page(3, "正文"), status="unknown")

    with pytest.raises(PageIndexError) as exc:
        await service.ensure_index(
            row, tenant_id=TENANT_ID, document_id=DOCUMENT_ID, embedding_profile=profile
        )

    assert exc.value.reason == "parse_coverage_unknown"
    assert provider.document_calls == []


@pytest.mark.asyncio
async def test_incomplete_or_noncontiguous_coverage_fails_before_embedding():
    provider = FakeEmbeddingProvider()
    service = PageIndexService(store=InMemoryPageEmbeddingStore(), provider=provider)
    profile = EmbeddingProfile(model="fake", version="test")
    row = _row(_page(1, "摘要"), _page(3, "正文"), status="incomplete")
    row["data"]["engine"]["coverage"]["observed_page_numbers"] = [1, 3]

    with pytest.raises(PageIndexError) as exc:
        await service.ensure_index(
            row, tenant_id=TENANT_ID, document_id=DOCUMENT_ID, embedding_profile=profile
        )

    assert exc.value.reason == "parse_coverage_incomplete"
    assert provider.document_calls == []


@pytest.mark.asyncio
async def test_identity_mismatch_is_rejected_before_provider_call():
    provider = FakeEmbeddingProvider()
    service = PageIndexService(store=InMemoryPageEmbeddingStore(), provider=provider)
    profile = EmbeddingProfile(model="fake", version="test")

    with pytest.raises(PageIndexError) as exc:
        await service.ensure_index(
            _row(_page(1, "摘要"), _page(2, "正文"), _page(3, "正文")),
            tenant_id="other-tenant",
            document_id=DOCUMENT_ID,
            embedding_profile=profile,
        )

    assert exc.value.reason == "tenant_mismatch"
    assert provider.document_calls == []
