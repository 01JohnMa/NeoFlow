# api/exceptions.py
"""统一异常定义 - 业务异常类型"""

from fastapi import HTTPException
from typing import Optional, Dict, Any


class AppException(HTTPException):
    """
    基础业务异常
    
    所有业务异常应继承此类，提供：
    - code: 错误码（用于前端判断和国际化）
    - detail: 错误描述
    - status_code: HTTP 状态码
    """
    
    def __init__(
        self, 
        code: str, 
        detail: str, 
        status_code: int = 400,
        headers: Optional[Dict[str, str]] = None
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code


class AuthenticationError(AppException):
    """认证错误 - 需要登录"""
    
    def __init__(self, detail: str = "需要登录"):
        super().__init__(
            code="AUTH_REQUIRED",
            detail=detail,
            status_code=401
        )


class AuthorizationError(AppException):
    """授权错误 - 无权访问"""
    
    def __init__(self, detail: str = "无权访问此资源"):
        super().__init__(
            code="FORBIDDEN",
            detail=detail,
            status_code=403
        )


class DocumentNotFoundError(AppException):
    """文档不存在"""
    
    def __init__(self, document_id: str):
        super().__init__(
            code="DOC_NOT_FOUND",
            detail=f"文档不存在或无权访问: {document_id}",
            status_code=404
        )


class FileNotFoundError(AppException):
    """文件不存在"""
    
    def __init__(self, file_path: str = ""):
        detail = f"文件不存在: {file_path}" if file_path else "文件不存在"
        super().__init__(
            code="FILE_NOT_FOUND",
            detail=detail,
            status_code=404
        )


class ValidationError(AppException):
    """验证错误 - 参数无效"""
    
    def __init__(self, detail: str):
        super().__init__(
            code="VALIDATION_ERROR",
            detail=detail,
            status_code=400
        )


class FileTypeError(AppException):
    """文件类型错误"""
    
    def __init__(self, allowed_types: str):
        super().__init__(
            code="INVALID_FILE_TYPE",
            detail=f"不支持的文件类型。支持: {allowed_types}",
            status_code=400
        )


class FileSizeError(AppException):
    """文件大小错误"""
    
    def __init__(self, max_size_mb: float):
        super().__init__(
            code="FILE_TOO_LARGE",
            detail=f"文件太大。最大: {max_size_mb:.1f}MB",
            status_code=400
        )


class ProcessingError(AppException):
    """处理错误 - OCR/提取过程失败"""
    
    def __init__(self, detail: str):
        super().__init__(
            code="PROCESSING_FAILED",
            detail=detail,
            status_code=500
        )


class DocumentTypeError(AppException):
    """文档类型错误"""
    
    def __init__(self, document_type: str):
        super().__init__(
            code="UNKNOWN_DOC_TYPE",
            detail=f"未知文档类型: {document_type}",
            status_code=400
        )


class DatabaseError(AppException):
    """数据库操作错误"""
    
    def __init__(self, detail: str = "数据库操作失败"):
        super().__init__(
            code="DB_ERROR",
            detail=detail,
            status_code=500
        )


class ExternalServiceError(AppException):
    """外部服务错误（如飞书）"""
    
    def __init__(self, service: str, detail: str = ""):
        message = f"{service}服务调用失败"
        if detail:
            message += f": {detail}"
        super().__init__(
            code="EXTERNAL_SERVICE_ERROR",
            detail=message,
            status_code=502
        )
