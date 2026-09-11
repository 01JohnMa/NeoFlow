# tests/services/test_mineru_live.py
"""MinerU 托管 API 冒烟测试（可选，联网且显式开启才运行）。

运行方式（key 从环境读取，永不写入仓库）：
    MINERU_API_KEY=... NEOFLOW_LIVE_MINERU=1 \
        python -m pytest tests/services/test_mineru_live.py -q

未配置 key 或未显式开启时跳过；网络不可达时 skip，API 业务错误则失败。
"""

import os

import pytest
from PIL import Image, ImageDraw

pytestmark = pytest.mark.skipif(
    not os.environ.get("MINERU_API_KEY") or os.environ.get("NEOFLOW_LIVE_MINERU") != "1",
    reason="需要 MINERU_API_KEY 且 NEOFLOW_LIVE_MINERU=1（默认不跑 live 测试）",
)


def _make_png(path) -> None:
    image = Image.new("RGB", (800, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 60), "NeoFlow Live Parse", fill="black")
    draw.text((40, 140), "alpha 42", fill="black")
    image.save(path, format="PNG")


@pytest.mark.asyncio
async def test_live_mineru_pipeline_parse(tmp_path):
    import httpx

    from services.mineru_adapter import MinerUApiAdapter

    image_path = tmp_path / "neoflow_live_probe.png"
    _make_png(image_path)

    adapter = MinerUApiAdapter(poll_interval=3, timeout=300)
    try:
        result = await adapter.parse(str(image_path), {
            "model_version": "pipeline",
            "method": "ocr",
            "poll_interval_seconds": 3,
            "timeout_seconds": 300,
        })
    except (httpx.TransportError, httpx.TimeoutException) as exc:
        pytest.skip(f"MinerU 网络不可用: {exc}")

    assert result.pages, "live 解析应至少返回一页"
    assert result.markdown.strip(), "live 解析应返回 markdown"
    assert result.pages[0].coordinate_space == "pixel"

    block_types = {block.type for page in result.pages for block in page.blocks}
    assert block_types
    assert block_types <= {"header", "footer", "figure", "formula", "table", "title", "text", "list"}
    for page in result.pages:
        for block in page.blocks:
            if block.source == "vlm":
                assert block.confidence is None
