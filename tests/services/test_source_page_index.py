import pytest
import httpx

from services import source_page_index as module


@pytest.mark.asyncio
async def test_build_index_routes_native_text_and_images(monkeypatch, tmp_path):
    pdf = tmp_path / "mixed.pdf"
    pdf.write_bytes(b"pdf")
    monkeypatch.setattr(module, "_page_count", lambda path: 3)
    monkeypatch.setattr(module, "_source_hash", lambda path: "sha")
    monkeypatch.setattr(
        module,
        "_native_text",
        lambda path, page: "native text " * 10 if page != 2 else "",
    )
    monkeypatch.setattr(module, "_render_page", lambda path, page: f"data:image/png;base64,{page}")
    monkeypatch.setattr(module.settings, "SOURCE_PAGE_MIN_TEXT_CHARS", 20)
    monkeypatch.setattr(module.settings, "EMBEDDING_MAX_BATCH_SIZE", 20)
    monkeypatch.setattr(module, "_dashscope_text_embeddings", _vectors)
    monkeypatch.setattr(module, "_dashscope_image_embeddings", _vectors)
    monkeypatch.setattr(module.settings, "SOURCE_PAGE_IMAGE_API_KEY", "key")

    calls = []

    async def gate(stage):
        calls.append(stage)

    result = await module.build_source_page_index(str(pdf), request_gate=gate)
    assert [page.modality for page in result.pages] == ["text", "image", "text"]
    assert len(result.vectors) == 3
    assert calls == ["source_page_text_embedding", "source_page_image_embedding"]


async def _vectors(values, **kwargs):
    return [[float(index + 1), 0.0] for index, _ in enumerate(values)]


@pytest.mark.asyncio
async def test_retrieve_top2_per_field_and_dedicated_image_query(monkeypatch):
    index = module.SourcePageIndex(
        source_hash="sha",
        pages=[
            module.SourcePage(1, "text", text="one"),
            module.SourcePage(2, "image", image_data_uri="data:image/png;base64,x"),
            module.SourcePage(3, "text", text="three"),
        ],
        vectors=[[1.0, 0.0], [1.0, 0.0], [0.9, 0.0]],
        profile="test",
        embedding_space="multimodal",
    )
    text_calls = []
    image_calls = []

    async def text_vectors(values, **kwargs):
        text_calls.append(values)
        return [[1.0, 0.0] for _ in values]

    async def image_vectors(values):
        image_calls.append(values)
        return [[1.0, 0.0] for _ in values]

    monkeypatch.setattr(module, "_openai_text_embeddings", text_vectors)
    monkeypatch.setattr(module, "_dashscope_text_embeddings", image_vectors)
    stages = []

    async def gate(stage):
        stages.append(stage)

    result = await module.retrieve_source_pages(
        index, {"/a": "a", "/b": "b"}, request_gate=gate
    )
    assert all(len(rows) == 2 for rows in result.values())
    assert len(text_calls) == 0
    assert len(image_calls) == 1
    assert stages == ["source_page_image_query_embedding"]


def test_compact_page_ranges_restores_physical_page_numbers():
    assert module.compact_page_ranges([7, 1, 2, 4, 5, 6, 6]) == "1-2,4-7"


@pytest.mark.asyncio
async def test_provider_transport_error_is_typed(monkeypatch):
    class BrokenClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            raise httpx.ConnectError("offline")

    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kwargs: BrokenClient())
    monkeypatch.setattr(module.settings, "EMBEDDING_API_KEY", "key")
    monkeypatch.setattr(module.settings, "EMBEDDING_BASE_URL", "https://embedding.test")
    with pytest.raises(module.SourcePageIndexError) as exc:
        await module._openai_text_embeddings(["query"])
    assert exc.value.reason == "source_text_embedding_failed"
