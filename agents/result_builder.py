# agents/result_builder.py
"""工作流统一结果构造"""

from typing import Any, Dict, Optional


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
    processing_time: float,
    template_id: Optional[str] = None,
    template_name: Optional[str] = None,
) -> Dict[str, Any]:
    """构造单文档处理成功结果

    Args:
        document_id: 文档ID
        document_type: 文档类型
        extraction_data: 提取的字段字典
        processing_time: 处理耗时（秒）
        template_id: 模板ID（可选）
        template_name: 模板名称（可选）

    Returns:
        统一格式的成功结果字典
    """
    result: Dict[str, Any] = {
        "success": True,
        "document_id": document_id,
        "document_type": document_type,
        "extraction_data": extraction_data,
        "processing_time": processing_time,
        "step": "completed",
        "error": None,
    }

    if template_id is not None:
        result["template_id"] = template_id
    if template_name is not None:
        result["template_name"] = template_name

    return result
