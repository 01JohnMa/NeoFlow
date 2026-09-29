import base64

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
        "_native_pages_text",
        lambda path, count: ["native text " * 10, "", "native text " * 10],
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


@pytest.mark.asyncio
async def test_build_index_falls_back_to_per_page_text_on_split_mismatch(monkeypatch, tmp_path):
    pdf = tmp_path / "mismatch.pdf"
    pdf.write_bytes(b"pdf")
    monkeypatch.setattr(module, "_page_count", lambda path: 2)
    monkeypatch.setattr(module, "_source_hash", lambda path: "sha")
    monkeypatch.setattr(module, "_native_pages_text", lambda path, count: None)
    requested_pages = []

    def per_page_text(path, page):
        requested_pages.append(page)
        return f"native text page {page} " * 10

    monkeypatch.setattr(module, "_native_text", per_page_text)
    monkeypatch.setattr(module.settings, "SOURCE_PAGE_MIN_TEXT_CHARS", 20)
    monkeypatch.setattr(module.settings, "EMBEDDING_MAX_BATCH_SIZE", 20)
    monkeypatch.setattr(module, "_openai_text_embeddings", _vectors)

    result = await module.build_source_page_index(str(pdf))
    assert requested_pages == [1, 2]
    assert [page.modality for page in result.pages] == ["text", "text"]
    assert result.pages[1].text.startswith("native text page 2")


@pytest.mark.asyncio
async def test_build_index_pipelines_image_render_and_embedding(monkeypatch, tmp_path):
    pdf = tmp_path / "scanned.pdf"
    pdf.write_bytes(b"pdf")
    monkeypatch.setattr(module, "_page_count", lambda path: 3)
    monkeypatch.setattr(module, "_source_hash", lambda path: "sha")
    monkeypatch.setattr(module, "_native_pages_text", lambda path, count: ["", "", ""])
    rendered_pages = []
    monkeypatch.setattr(
        module, "_render_page",
        lambda path, page: rendered_pages.append(page) or f"data:image/png;base64,{page}",
    )
    monkeypatch.setattr(module.settings, "SOURCE_PAGE_MIN_TEXT_CHARS", 20)
    embedded_images = []

    async def image_vectors(values, **kwargs):
        embedded_images.extend(values)
        return [[1.0, 0.0] for _ in values]

    monkeypatch.setattr(module, "_dashscope_image_embeddings", image_vectors)
    monkeypatch.setattr(module.settings, "SOURCE_PAGE_IMAGE_API_KEY", "key")
    calls = []

    async def gate(stage):
        calls.append(stage)

    result = await module.build_source_page_index(str(pdf), request_gate=gate)
    # Render tasks run in a thread pool, so their start order is not
    # deterministic; embedding consumption order is.
    assert sorted(rendered_pages) == [1, 2, 3]
    assert embedded_images == [f"data:image/png;base64,{page}" for page in (1, 2, 3)]
    assert calls == ["source_page_image_embedding"] * 3
    assert [page.modality for page in result.pages] == ["image", "image", "image"]
    assert len(result.vectors) == 3


def test_render_page_retries_oversize_at_lower_dpi(monkeypatch):
    monkeypatch.setattr(module.settings, "SOURCE_PAGE_RENDER_DPI", 144)
    monkeypatch.setattr(module.settings, "SOURCE_PAGE_MAX_IMAGE_BYTES", 100)
    attempted_dpis = []

    def fake_png(path, page, dpi):
        attempted_dpis.append(dpi)
        return b"x" * 200 if len(attempted_dpis) == 1 else b"x" * 10

    monkeypatch.setattr(module, "_render_page_png", fake_png)
    result = module._render_page("doc.pdf", 7)
    assert attempted_dpis == [144, 108]
    assert result == "data:image/png;base64," + base64.b64encode(b"x" * 10).decode("ascii")


def test_render_page_fails_when_oversize_at_every_dpi(monkeypatch):
    monkeypatch.setattr(module.settings, "SOURCE_PAGE_RENDER_DPI", 144)
    monkeypatch.setattr(module.settings, "SOURCE_PAGE_MAX_IMAGE_BYTES", 100)
    monkeypatch.setattr(module, "_render_page_png", lambda path, page, dpi: b"x" * 200)
    with pytest.raises(module.SourcePageIndexError) as exc:
        module._render_page("doc.pdf", 7)
    assert exc.value.reason == "source_image_too_large"


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
        chunks=[
            module.SourceChunk("p1-c0", 1, "text", "one"),
            module.SourceChunk("p2-c0", 2, "image", ""),
            module.SourceChunk("p3-c0", 3, "text", "three"),
        ],
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


@pytest.mark.asyncio
async def test_retrieve_merges_structural_and_neighbor_candidates(monkeypatch):
    index = module.SourcePageIndex(
        source_hash="sha",
        pages=[
            module.SourcePage(1, "text", text="封面"),
            module.SourcePage(2, "text", text="4.2 入选标准\n1) 年龄符合\n2) 诊断明确"),
            module.SourcePage(3, "text", text="入选标准续表\n3) 签署知情同意"),
            module.SourcePage(4, "text", text="其他章节"),
        ],
        vectors=[[1.0, 0.0], [0.8, 0.0], [0.7, 0.0], [0.6, 0.0]],
        profile="test",
        embedding_space="text",
        chunks=[
            module.SourceChunk("p1-c0", 1, "text", "封面"),
            module.SourceChunk("p2-c0", 2, "text", "4.2 入选标准\n1) 年龄符合\n2) 诊断明确", "section", ("4.2 入选标准",)),
            module.SourceChunk("p3-c0", 3, "text", "入选标准续表\n3) 签署知情同意", "page"),
            module.SourceChunk("p4-c0", 4, "text", "其他章节"),
        ],
    )

    async def text_vectors(values, **kwargs):
        return [[1.0, 0.0] for _ in values]

    monkeypatch.setattr(module, "_openai_text_embeddings", text_vectors)
    result = await module.retrieve_source_pages(index, {"/criteria": "入选标准 完整列表"})
    rows = result["/criteria"]
    assert {row.page_no for row in rows} >= {1, 2, 3}
    assert any("structural" in row.sources for row in rows)
    assert any("neighbor" in row.sources for row in rows)


def test_compact_page_ranges_restores_physical_page_numbers():
    assert module.compact_page_ranges([7, 1, 2, 4, 5, 6, 6]) == "1-2,4-7"


def test_chunker_splits_sections_without_splitting_numbered_items():
    page = module.SourcePage(
        22,
        "text",
        "9.1.1 主要疗效指标\n1）头痛消失比例\n2）复发率\n9.1.2 次要疗效指标\n1）无头痛比例",
    )
    chunks = module._build_chunks([page])
    assert len(chunks) == 2
    assert chunks[0].heading_path == ("9.1.1 主要疗效指标",)
    assert chunks[1].heading_path == ("9.1.2 次要疗效指标",)
    assert "1）头痛消失比例" in chunks[0].text


@pytest.mark.asyncio
async def test_hybrid_retrieval_prefers_matching_heading_over_dense_tie(monkeypatch):
    index = module.SourcePageIndex(
        source_hash="sha",
        pages=[module.SourcePage(22, "text", "9.1.2 次要疗效指标\n..."), module.SourcePage(3, "text", "其他章节")],
        vectors=[[1.0, 0.0], [1.0, 0.0]],
        profile="test",
        chunks=[
            module.SourceChunk("p22-c0", 22, "text", "9.1.2 次要疗效指标\n...", "section", ("9.1.2 次要疗效指标",)),
            module.SourceChunk("p3-c0", 3, "text", "其他章节", "page"),
        ],
    )

    async def vectors(values, **kwargs):
        return [[1.0, 0.0] for _ in values]

    monkeypatch.setattr(module, "_openai_text_embeddings", vectors)
    result = await module.retrieve_source_pages(index, {"/secondary": "secondary_endpoint 次要疗效指标"})
    assert result["/secondary"][0].page_no == 22
    assert "lexical" in result["/secondary"][0].sources


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
