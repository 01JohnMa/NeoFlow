# agents/result_builder.py
"""工作流统一结果构造"""

from typing import Any, Dict, List, Optional


_OCR_TEXT_PREVIEW_LEN = 500


def build_error(
    document_id: str,
    error: str,
    processing_time: Optional[float] = None,
) -> Dict[str, Any]:
    """构造失败结果

    Args:
        document_id: 文档ID
        error: 错误信息
        processing_time: 耗时（秒），None 时不包含该字段

    Returns:
        统一格式的失败结果字典
    """
    result: Dict[str, Any] = {
        "success": False,
        "document_id": document_id,
        "error": error,
    }
    if processing_time is not None:
        result["processing_time"] = processing_time
    return result


def build_single_success(
    document_id: str,
    document_type: str,
    extraction_data: dict,
    ocr_text: str,
    ocr_confidence: float,
    processing_time: float,
    template_id: Optional[str] = None,
    template_name: Optional[str] = None,
) -> Dict[str, Any]:
    """构造单文档处理成功结果

    适用于 process() 和 process_with_template()。

    Args:
        document_id: 文档ID
        document_type: 文档类型
        extraction_data: 提取的字段字典
        ocr_text: OCR 原始文本（会截断到前 500 字符）
        ocr_confidence: OCR 置信度
        processing_time: 处理耗时（秒）
        template_id: 模板ID（可选）
        template_name: 模板名称（可选）

    Returns:
        统一格式的成功结果字典
    """
    ocr_preview = (
        ocr_text[:_OCR_TEXT_PREVIEW_LEN] + "..."
        if len(ocr_text) > _OCR_TEXT_PREVIEW_LEN
        else ocr_text
    )

    result: Dict[str, Any] = {
        "success": True,
        "document_id": document_id,
        "document_type": document_type,
        "extraction_data": extraction_data,
        "ocr_text": ocr_preview,
        "ocr_confidence": ocr_confidence,
        "processing_time": processing_time,
        "step": "completed",
        "error": None,
    }

    if template_id is not None:
        result["template_id"] = template_id
    if template_name is not None:
        result["template_name"] = template_name

    return result


def build_merge_success(
    document_id: str,
    template_id: str,
    template_name: str,
    document_type: str,
    extraction_results: List[Dict[str, Any]],
    results_a: List[dict],
    results_b: List[dict],
    processing_time: float,
) -> Dict[str, Any]:
    """构造合并模式成功结果

    适用于 process_merge()，支持多样品。

    Args:
        document_id: 文档ID
        template_id: 模板ID
        template_name: 模板名称
        document_type: 文档类型（模板 code）
        extraction_results: 各样品合并后的结果列表 [{"sample_index": n, "data": {...}}, ...]
        results_a: doc_type_a（如积分球）的提取结果列表
        results_b: doc_type_b（如光分布）的提取结果列表
        processing_time: 处理耗时（秒）

    Returns:
        统一格式的合并成功结果字典
    """
    return {
        "success": True,
        "document_id": document_id,
        "template_id": template_id,
        "template_name": template_name,
        "document_type": document_type,
        "extraction_data": extraction_results[0]["data"] if extraction_results else {},
        "extraction_results": extraction_results,
        "sample_count": len(extraction_results),
        "sub_results": {
            "results_a": results_a,
            "results_b": results_b,
        },
        "processing_time": processing_time,
        "step": "completed",
        "error": None,
    }
