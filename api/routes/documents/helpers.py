# api/routes/documents/helpers.py
"""文档路由 - 辅助函数"""

import os
import json
import aiofiles
from typing import Optional
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


def normalize_review_value(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().casefold()


def parse_allowed_values(raw_values: object) -> list:
    if raw_values is None:
        return []
    if isinstance(raw_values, list):
        return [str(item) for item in raw_values if item is not None]
    if isinstance(raw_values, str):
        text = raw_values.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item is not None]
        except json.JSONDecodeError:
            pass
        return [text]
    return [str(raw_values)]


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


async def push_to_feishu(
    template: dict,
    extraction_data: dict,
    display_name: Optional[str],
    document_id: str,
    source_file_path: Optional[str] = None,
    log_prefix: str = "",
) -> None:
    """
    统一飞书推送逻辑：构建 field_mapping → 处理 file_name → 上传附件 → push_by_template

    Args:
        template: 模板字典，需含 feishu_bitable_token / feishu_table_id
        extraction_data: 提取结果数据
        display_name: 文档显示名称（用于 file_name 字段）
        document_id: 文档 ID（用于日志和兜底 file_name）
        source_file_path: 源文件路径（可选，用于上传附件）
        log_prefix: 日志前缀（如 "[job=xxx]"）
    """
    from services.feishu_service import feishu_service
    from services.template_service import template_service

    bitable_token = template.get("feishu_bitable_token")
    table_id = template.get("feishu_table_id")

    if not (bitable_token and table_id):
        logger.info(f"{log_prefix}模板未配置飞书，跳过推送: {document_id}")
        return

    field_mapping = template_service.build_field_mapping(template)
    push_data = {**extraction_data}

    file_name_for_push = (
        (display_name or "").strip()
        or str(template.get("name") or "").strip()
        or document_id
    )
    if file_name_for_push:
        if "file_name" not in field_mapping:
            field_mapping["file_name"] = "文件名"
        push_data["file_name"] = file_name_for_push

    if template.get("push_attachment", True) and source_file_path and os.path.exists(source_file_path):
        file_token = await feishu_service._upload_file_to_feishu(source_file_path, bitable_token)
        if file_token:
            push_data["attachment"] = [{"file_token": file_token}]
            field_mapping["attachment"] = "附件"

    success = await feishu_service.push_by_template(push_data, field_mapping, bitable_token, table_id)
    if success:
        logger.info(f"{log_prefix}飞书推送成功: {document_id}")
    else:
        logger.warning(f"{log_prefix}飞书推送失败: {document_id}")
