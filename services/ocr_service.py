# services/ocr_service.py
"""OCR服务 - 基于PaddleOCR，引擎池模式支持并发"""

import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty
from typing import List, Dict, Any, Optional
from paddleocr import PaddleOCR
from loguru import logger

from config.settings import settings


class OCRValidationError(Exception):
    """OCR 结果验证失败异常"""
    pass


class OCRService:
    """PaddleOCR 服务封装 - 引擎池模式，支持并发调用

    每个引擎实例独立持有 Paddle Predictor，彼此隔离，线程安全。
    并发请求数超过池大小时自动排队等待，不会崩溃。
    """

    _instance: Optional['OCRService'] = None
    _initialized: bool = False

    # OCR 结果验证配置
    MIN_CONFIDENCE_THRESHOLD = 0.3  # 最低可接受置信度
    MIN_TEXT_LENGTH = 10            # 最短文本长度（字符）

    # 引擎池大小：每个引擎约占 1-2 GB 内存，根据服务器配置调整
    ENGINE_POOL_SIZE = 2

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not OCRService._initialized:
            self._engine_pool: Queue = Queue(maxsize=self.ENGINE_POOL_SIZE)
            self._pool_initialized: bool = False
            # max_workers 与池大小一致，保证每个引擎都有对应线程
            self.executor = ThreadPoolExecutor(max_workers=self.ENGINE_POOL_SIZE)
            self._watermarks = ['no', 'noi', 'copy', '样本', '仅供参考']
            self._threshold = 0.35
            OCRService._initialized = True

    # ── 向后兼容属性 ──────────────────────────────────────────────────────
    @property
    def ocr_engine(self) -> Optional[PaddleOCR]:
        """向后兼容：窥探池中第一个引擎（只读，不应直接调用其 ocr() 方法）"""
        try:
            engine = self._engine_pool.get_nowait()
            self._engine_pool.put(engine)
            return engine
        except Empty:
            return None

    # ── 初始化 ────────────────────────────────────────────────────────────
    async def initialize(self) -> bool:
        """异步初始化 OCR 引擎池（幂等）"""
        if self._pool_initialized and not self._engine_pool.empty():
            return True

        try:
            if not settings.OCR_ENABLED:
                logger.warning("OCR 已禁用，跳过初始化")
                return False

            model_paths = {
                "检测模型": settings.OCR_DET_MODEL_PATH,
                "识别模型": settings.OCR_REC_MODEL_PATH,
                "方向模型": settings.OCR_ORI_MODEL_PATH,
                "文档模型": settings.OCR_DOC_MODEL_PATH,
            }
            for name, path in model_paths.items():
                if not os.path.exists(path):
                    raise FileNotFoundError(f"{name}路径不存在: {path}")
                logger.info(f"✓ {name}: {path}")

            loop = asyncio.get_event_loop()
            for i in range(self.ENGINE_POOL_SIZE):
                engine = await loop.run_in_executor(self.executor, self._init_ocr_sync)
                self._engine_pool.put(engine)
                logger.info(f"✓ OCR引擎 [{i + 1}/{self.ENGINE_POOL_SIZE}] 初始化成功")

            self._pool_initialized = True
            logger.info(f"✓ OCR引擎池就绪，共 {self.ENGINE_POOL_SIZE} 个引擎，"
                        f"支持 {self.ENGINE_POOL_SIZE} 并发任务")
            return True

        except Exception as e:
            logger.error(f"✗ OCR引擎池初始化失败: {e}")
            raise

    def _init_ocr_sync(self) -> PaddleOCR:
        """同步创建一个 PaddleOCR 引擎实例"""
        return PaddleOCR(
            lang='ch',
            det_model_dir=settings.OCR_DET_MODEL_PATH,
            rec_model_dir=settings.OCR_REC_MODEL_PATH,
            textline_orientation_model_dir=settings.OCR_ORI_MODEL_PATH,
            doc_orientation_classify_model_dir=settings.OCR_DOC_MODEL_PATH,
            use_doc_orientation_classify=True,
            use_doc_unwarping=False,
            ir_optim=settings.OCR_IR_OPTIM,
            enable_mkldnn=settings.OCR_USE_MKLDNN,
            det_limit_side_len=800,
            det_limit_type='min',
        )

    # ── 引擎池借还 ────────────────────────────────────────────────────────
    def _acquire_engine(self) -> PaddleOCR:
        """从池中取出一个引擎（池满时阻塞等待直到有引擎归还）"""
        engine = self._engine_pool.get()
        return engine

    def _release_engine(self, engine: PaddleOCR) -> None:
        """将引擎归还到池中"""
        self._engine_pool.put(engine)

    # ── 公共异步接口 ──────────────────────────────────────────────────────
    async def process_document(self, file_path: str) -> Dict[str, Any]:
        """处理单个文档

        Returns:
            {
                "text": str,           # 提取的文本
                "confidence": float,   # 平均置信度
                "lines": List[Dict]    # 每行详细信息
                "total_lines": int     # 总行数
            }
        """
        if not settings.OCR_ENABLED:
            raise OCRValidationError("OCR 已禁用，无法处理文档")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        if not self._pool_initialized:
            await self.initialize()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self._process_sync, file_path)

    async def process_document_per_page(self, file_path: str) -> List[Dict[str, Any]]:
        """逐页处理文档，返回每页独立的 OCR 结果

        用于需要按页分别提取的场景（如照明积分球多样品）

        Returns:
            每页的 OCR 结果列表:
            [
                {"page": 1, "text": "页1文本", "confidence": 0.95, "lines": [...], "total_lines": 10},
                {"page": 2, "text": "页2文本", "confidence": 0.92, "lines": [...], "total_lines": 8},
                ...
            ]
        """
        if not settings.OCR_ENABLED:
            raise OCRValidationError("OCR 已禁用，无法处理文档")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        if not self._pool_initialized:
            await self.initialize()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self._process_per_page_sync, file_path)

    # ── 同步处理（在线程池中执行，通过引擎池隔离）────────────────────────
    def _process_sync(self, file_path: str) -> Dict[str, Any]:
        """同步执行 OCR（从引擎池借用一个引擎，用后归还）"""
        engine = self._acquire_engine()
        try:
            raw = engine.ocr(file_path, cls=True)

            all_text_pages: List[str] = []
            lines: List[Dict] = []
            total_score = 0.0
            valid_count = 0

            for page_result in (raw or []):
                if not page_result:
                    continue
                page_text, page_lines, page_conf = self._page_result_to_text(page_result)
                if page_text:
                    all_text_pages.append(page_text)
                    lines.extend(page_lines)
                    total_score += page_conf * len(page_lines)
                    valid_count += len(page_lines)

            avg_confidence = total_score / valid_count if valid_count > 0 else 0.0
            result = {
                "text": "\n\n".join(all_text_pages),
                "confidence": avg_confidence,
                "lines": lines,
                "total_lines": len(lines),
            }
            self._validate_ocr_result(result)
            return result
        finally:
            self._release_engine(engine)

    def _process_per_page_sync(self, file_path: str) -> List[Dict[str, Any]]:
        """同步执行逐页 OCR（从引擎池借用一个引擎，用后归还）"""
        engine = self._acquire_engine()
        try:
            ocr_result = engine.ocr(file_path, cls=True)

            page_results = []
            for page_idx, page_result in enumerate(ocr_result or []):
                if not page_result:
                    continue
                page_text, page_lines, avg_conf = self._page_result_to_text(page_result)
                if page_lines:
                    page_results.append({
                        "page": page_idx + 1,
                        "text": page_text,
                        "confidence": avg_conf,
                        "lines": page_lines,
                        "total_lines": len(page_lines),
                    })

            if not page_results:
                raise OCRValidationError("OCR 未能识别到任何文本")

            logger.info(f"逐页OCR完成: {file_path}, 共{len(page_results)}页有效内容")
            return page_results
        finally:
            self._release_engine(engine)

    def process_document_sync(self, file_path: str) -> List[str]:
        """同步处理文档 - 兼容旧接口（从引擎池借用引擎）

        Returns:
            提取的文本行列表
        """
        if not settings.OCR_ENABLED:
            raise OCRValidationError("OCR 已禁用，无法处理文档")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        if not self._pool_initialized:
            raise OCRValidationError("OCR 引擎池未初始化，请先调用 initialize()")

        engine = self._acquire_engine()
        try:
            result = engine.ocr(file_path, cls=True)
            all_pages: List[str] = []
            for page_result in (result or []):
                if not page_result:
                    continue
                page_text, _, _ = self._page_result_to_text(page_result)
                if page_text:
                    all_pages.append(page_text)
            return "\n\n".join(all_pages).split("\n") if all_pages else []
        finally:
            self._release_engine(engine)

    async def process_batch(self, file_paths: List[str]) -> Dict[str, Any]:
        """批量处理文档（并发数受引擎池大小限制，自动排队）"""
        tasks = [self.process_document(path) for path in file_paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = {}
        for path, result in zip(file_paths, results):
            if isinstance(result, Exception):
                output[path] = {"error": str(result)}
            else:
                output[path] = result
        return output

    # ── 文本后处理工具 ────────────────────────────────────────────────────
    def _compute_line_threshold(self, page_result: list, ratio: float = 0.4) -> float:
        """从单页 OCR 结果动态计算行间距阈值。

        取各文本框高度的中位数乘以 ratio，避免对不同分辨率/字号硬编码像素值。
        """
        heights = []
        for line_info in page_result:
            try:
                box = line_info[0]
                ys = [p[1] for p in box if isinstance(p, (list, tuple)) and len(p) >= 2]
                if len(ys) >= 2:
                    heights.append(max(ys) - min(ys))
            except Exception:
                continue
        if not heights:
            return 15.0
        heights.sort()
        return heights[len(heights) // 2] * ratio

    def _page_result_to_text(self, page_result: list) -> tuple:
        """将单页原始 OCR 结果过滤、按阅读顺序排序后返回三元组。

        过滤规则复用 self._threshold 和 self._watermarks；
        使用当前行平均Y作为分组基准，比首/末元素基准更稳定。

        Returns:
            (ordered_text, lines_with_confidence, avg_confidence)
            lines_with_confidence: List[{"text": str, "confidence": float}]，兼容下游结构
        """
        if not page_result:
            return "", [], 0.0

        threshold = self._compute_line_threshold(page_result)
        items = []

        for line_info in page_result:
            try:
                if not line_info or len(line_info) < 2:
                    continue
                box, text_info = line_info[0], line_info[1]
                if not isinstance(box, (list, tuple)) or len(box) < 4:
                    continue
                if not isinstance(text_info, tuple) or len(text_info) < 2:
                    continue
                xs = [p[0] for p in box if isinstance(p, (list, tuple)) and len(p) >= 2]
                ys = [p[1] for p in box if isinstance(p, (list, tuple)) and len(p) >= 2]
                if not xs or not ys:
                    continue
                text = str(text_info[0]).strip()
                score = float(text_info[1])
                if not text or score < self._threshold:
                    continue
                if any(wm in text.lower() for wm in self._watermarks):
                    continue
                items.append({
                    "text": text,
                    "y": sum(ys) / len(ys),
                    "x": min(xs),
                    "confidence": score,
                })
            except Exception:
                continue

        if not items:
            return "", [], 0.0

        items.sort(key=lambda i: i["y"])

        visual_lines: list = []
        current_line = [items[0]]
        current_avg_y = items[0]["y"]

        for item in items[1:]:
            if abs(item["y"] - current_avg_y) <= threshold:
                current_line.append(item)
                current_avg_y = sum(i["y"] for i in current_line) / len(current_line)
            else:
                current_line.sort(key=lambda i: i["x"])
                visual_lines.append(current_line)
                current_line, current_avg_y = [item], item["y"]

        current_line.sort(key=lambda i: i["x"])
        visual_lines.append(current_line)

        ordered_items = [i for line in visual_lines for i in line]
        avg_confidence = sum(i["confidence"] for i in ordered_items) / len(ordered_items)
        lines_out = [{"text": i["text"], "confidence": i["confidence"]} for i in ordered_items]
        full_text = "\n".join(" ".join(i["text"] for i in line) for line in visual_lines)

        return full_text, lines_out, avg_confidence

    def _validate_ocr_result(self, result: Dict[str, Any]) -> None:
        """验证 OCR 结果的完整性和质量"""
        required_fields = ["text", "confidence", "lines", "total_lines"]
        for field in required_fields:
            if field not in result:
                raise OCRValidationError(f"OCR 结果缺少必要字段: {field}")

        text = result.get("text", "")
        if not text or not text.strip():
            raise OCRValidationError("OCR 未能识别到任何文本")

        if len(text.strip()) < self.MIN_TEXT_LENGTH:
            logger.warning(f"OCR 识别文本过短: {len(text.strip())} 字符 (最小推荐: {self.MIN_TEXT_LENGTH})")

        confidence = result.get("confidence", 0)
        if confidence < self.MIN_CONFIDENCE_THRESHOLD:
            logger.warning(
                f"OCR 置信度较低: {confidence:.2f} (阈值: {self.MIN_CONFIDENCE_THRESHOLD})"
            )

        lines = result.get("lines", [])
        total_lines = result.get("total_lines", 0)
        if len(lines) != total_lines:
            logger.warning(f"行数不一致: lines={len(lines)}, total_lines={total_lines}")

    def get_supported_formats(self) -> List[str]:
        """获取支持的文件格式"""
        return ['pdf', 'png', 'jpg', 'jpeg', 'tiff', 'bmp']

    async def close(self):
        """关闭服务，回收引擎池和线程池"""
        try:
            while not self._engine_pool.empty():
                self._engine_pool.get_nowait()
        except Empty:
            pass
        if self.executor:
            self.executor.shutdown(wait=True)
        logger.info("OCR服务已关闭")


# 单例实例
ocr_service = OCRService()
