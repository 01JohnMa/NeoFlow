# tests/test_ocr_lazy_import.py
"""确认 paddleocr 为可选依赖：未安装时也可导入 API 模块。"""

import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

BLOCK_PADDLE_SNIPPET = """
import sys

class PaddleBlocker:
    def find_spec(self, name, path=None, target=None):
        if name == "paddleocr" or name.startswith("paddleocr."):
            raise ImportError("paddleocr is blocked for this test")
        return None

sys.meta_path.insert(0, PaddleBlocker())
import services.ocr_service  # noqa: F401
print("ok")
"""


def test_ocr_service_imports_without_paddleocr():
    result = subprocess.run(
        [sys.executable, "-c", BLOCK_PADDLE_SNIPPET],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout
