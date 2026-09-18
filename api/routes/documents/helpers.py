# api/routes/documents/helpers.py
"""文档路由 - 辅助函数"""

import os
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
    """检测是否为认证/授权相关错误（token 过期等）"""
    error_str = str(error).lower()
    auth_keywords = ['jwt', 'token', '401', '502', 'expired', 'invalid', 'unauthorized']
    return any(keyword in error_str for keyword in auth_keywords)


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
