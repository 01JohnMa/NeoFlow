# agents/exceptions.py
"""工作流异常定义"""

from enum import Enum
from typing import Optional


class WorkflowErrorType(str, Enum):
    """工作流错误类型枚举"""
    OCR_FAILED = "ocr_failed"
    CLASSIFY_FAILED = "classify_failed"
    EXTRACT_FAILED = "extract_failed"
    TEMPLATE_NOT_FOUND = "template_not_found"
    VALIDATION_ERROR = "validation_error"
    LLM_ERROR = "llm_error"
    UNKNOWN_ERROR = "unknown_error"


class WorkflowError(Exception):
    """工作流业务异常，用于在节点内抛出，由顶层统一捕获"""

    def __init__(
        self,
        error_type: WorkflowErrorType,
        message: str,
        step: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.step = step or error_type.value
