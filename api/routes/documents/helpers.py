# api/routes/documents/helpers.py
"""文档路由 - 辅助函数"""

import os
import re

import aiofiles
from fastapi import UploadFile
from loguru import logger

from config.settings import settings


async def save_upload_file(file: UploadFile, destination: str) -> int:
    """
    保存上传的文件
    
    Args:
        file: 上传的文件对象
        destination: 目标路径
        
    Returns:
        文件大小（字节）
    """
    async with aiofiles.open(destination, 'wb') as out_file:
        content = await file.read()
        await out_file.write(content)
        return len(content)


def validate_file_extension(filename: str) -> bool:
    """
    验证文件扩展名
    
    Args:
        filename: 文件名
        
    Returns:
        是否为允许的扩展名
    """
    ext = os.path.splitext(filename)[1].lower()
    return ext in settings.allowed_extensions_list


def is_auth_error(error: Exception) -> bool:
    """只识别明确的 401/JWT 错误，避免把上游 5xx 当成登录过期。"""
    status_code = getattr(error, "status_code", None)
    response = getattr(error, "response", None)
    if status_code is None and response is not None:
        status_code = getattr(response, "status_code", None)
    if status_code == 401:
        return True

    error_str = str(error).lower()
    return bool(
        re.search(r"\b401\b", error_str)
        or "jwt" in error_str
        or "unauthorized" in error_str
        or "authentication" in error_str
        or "invalid token" in error_str
        or "token invalid" in error_str
        or "token expired" in error_str
    )


def raise_auth_or_processing_error(error: Exception, message: str) -> None:
    """
    统一 auth error 处理：若为认证错误则抛 AuthenticationError，否则抛 ProcessingError。
    用于替代各端点 except 块中重复的 _is_auth_error 检查。
    """
    from api.exceptions import AuthenticationError, ProcessingError
    if is_auth_error(error):
        logger.warning(f"Token 认证失败，需要重新登录: {error}")
        raise AuthenticationError("登录已过期，请重新登录")
    raise ProcessingError(f"{message}: {str(error)}")
