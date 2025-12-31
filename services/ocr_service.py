# services/ocr_service.py
"""OCR服务 - 基于MVP代码 text_pipline_ocr.py 重构"""

import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional
from paddleocr import PaddleOCR
from loguru import logger

from config.settings import settings


class OCRService:
    """PaddleOCR 服务封装"""
    
    _instance: Optional['OCRService'] = None
    _initialized: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not OCRService._initialized:
            self.ocr_engine: Optional[PaddleOCR] = None
            self.executor = ThreadPoolExecutor(max_workers=2)
            self._watermarks = ['no', 'noi', 'copy', '样本', '仅供参考']
            self._threshold = 0.5
            OCRService._initialized = True
    
    async def initialize(self) -> bool:
        """异步初始化OCR引擎"""
        try:
            # 验证模型路径
            model_paths = {
                "检测模型": settings.OCR_DET_MODEL_PATH,
                "识别模型": settings.OCR_REC_MODEL_PATH,
                "方向模型": settings.OCR_ORI_MODEL_PATH,
                "文档模型": settings.OCR_DOC_MODEL_PATH
            }
            
            for name, path in model_paths.items():
                if not os.path.exists(path):
                    raise FileNotFoundError(f"{name}路径不存在: {path}")
                logger.info(f"✓ {name}: {path}")
            
            # 异步初始化
            loop = asyncio.get_event_loop()
            self.ocr_engine = await loop.run_in_executor(
                self.executor, self._init_ocr_sync
            )
            
            logger.info("✓ OCR引擎初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"✗ OCR引擎初始化失败: {e}")
            raise
    
    def _init_ocr_sync(self) -> PaddleOCR:
        """同步初始化PaddleOCR - 来自MVP代码"""
        return PaddleOCR(
            lang='ch',
            det_model_dir=settings.OCR_DET_MODEL_PATH,
            rec_model_dir=settings.OCR_REC_MODEL_PATH,
            textline_orientation_model_dir=settings.OCR_ORI_MODEL_PATH,
            doc_orientation_classify_model_dir=settings.OCR_DOC_MODEL_PATH,
            use_doc_orientation_classify=True,
            use_doc_unwarping=False,
            det_limit_side_len=960,
            det_limit_type='max',
            use_angle_cls=True,
            show_log=False
        )
    
    async def process_document(self, file_path: str) -> Dict[str, Any]:
        """处理单个文档
        
        Args:
            file_path: 文件路径
            
        Returns:
            {
                "text": str,           # 提取的文本
                "confidence": float,   # 平均置信度
                "lines": List[Dict]    # 每行详细信息
                "total_lines": int     # 总行数
            }
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        if not self.ocr_engine:
            await self.initialize()
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self.executor, 
            self._process_sync, 
            file_path
        )
        
        return result
    
    def _process_sync(self, file_path: str) -> Dict[str, Any]:
        """同步执行OCR - 基于MVP代码逻辑"""
        result = self.ocr_engine.predict(input=file_path)
        
        lines = []
        total_score = 0
        valid_count = 0
        
        for page_result in result:
            texts = page_result.get("rec_texts", [])
            scores = page_result.get("rec_scores", [])
            
            for text, score in zip(texts, scores):
                text = text.strip()
                # 过滤低置信度和水印 - 来自MVP逻辑
                if (score >= self._threshold 
                    and text 
                    and not any(wm in text.lower() for wm in self._watermarks)):
                    lines.append({
                        "text": text,
                        "confidence": float(score)
                    })
                    total_score += score
                    valid_count += 1
        
        # 计算平均置信度
        avg_confidence = total_score / valid_count if valid_count > 0 else 0.0
        
        # 合并文本
        full_text = "\n".join([line["text"] for line in lines])
        
        return {
            "text": full_text,
            "confidence": avg_confidence,
            "lines": lines,
            "total_lines": len(lines)
        }
    
    def process_document_sync(self, file_path: str) -> List[str]:
        """同步处理文档 - 兼容MVP代码接口
        
        Args:
            file_path: 文件路径
            
        Returns:
            提取的文本行列表
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        if not self.ocr_engine:
            self.ocr_engine = self._init_ocr_sync()
        
        result = self.ocr_engine.predict(input=file_path)
        
        filtered_results = []
        for page_result in result:
            texts = page_result.get("rec_texts", [])
            scores = page_result.get("rec_scores", [])
            
            for text, score in zip(texts, scores):
                text = text.strip()
                if (score >= self._threshold 
                    and text 
                    and not any(wm in text.lower() for wm in self._watermarks)):
                    filtered_results.append(text)
        
        return filtered_results
    
    async def process_batch(self, file_paths: List[str]) -> Dict[str, Any]:
        """批量处理文档"""
        tasks = [self.process_document(path) for path in file_paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        output = {}
        for path, result in zip(file_paths, results):
            if isinstance(result, Exception):
                output[path] = {"error": str(result)}
            else:
                output[path] = result
        
        return output
    
    def get_supported_formats(self) -> List[str]:
        """获取支持的文件格式"""
        return ['pdf', 'png', 'jpg', 'jpeg', 'tiff', 'bmp']
    
    async def close(self):
        """关闭服务"""
        if self.executor:
            self.executor.shutdown(wait=True)
            logger.info("OCR服务已关闭")


# 单例实例
ocr_service = OCRService()

