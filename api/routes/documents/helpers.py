# api/routes/documents/helpers.py
"""文档路由 - 辅助函数"""

import os
import json
import aiofiles
from typing import Optional
from datetime import datetime
from fastapi import UploadFile
from loguru import logger

from config.settings import settings
from services.supabase_service import supabase_service
from services.template_service import template_service


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


async def handle_processing_success(
    document_id: str,
    result: dict,
    template_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    generate_display_name: bool = True,
    auto_approve: bool = False,
    source_file_path: Optional[str] = None,
) -> None:
    """处理成功时的统一逻辑"""
    await supabase_service.save_extraction_result(
        document_id=document_id,
        document_type=result.get("document_type") or result.get("template_name", "未知"),
        extraction_data=result["extraction_data"],
        template_id=template_id,
    )
    logger.info(f"提取结果已保存: {document_id}")

    display_name = None
    if generate_display_name:
        display_name = supabase_service.generate_display_name(
            document_type=result.get("document_type") or result.get("template_name"),
            extraction_data=result["extraction_data"]
        )

    doc_status = "completed" if auto_approve else "pending_review"
    update_data = {
        "status": doc_status,
        "document_type": result.get("document_type") or result.get("template_name"),
        "template_id": template_id,
        "tenant_id": tenant_id,
        "ocr_text": result.get("ocr_text", ""),
        "ocr_confidence": result.get("ocr_confidence"),
        "processed_at": datetime.now().isoformat(),
        "error_message": None
    }
    if display_name:
        update_data["display_name"] = display_name

    await supabase_service.update_document(document_id, update_data)
    logger.info(
        f"后台处理完成: {document_id}, 状态: {doc_status}"
        + (f", 显示名称: {display_name}" if display_name else "")
    )

    if auto_approve:
        try:
            template = None
            if template_id:
                template = await template_service.get_template_with_details(template_id)
            elif tenant_id and (result.get("document_type") or result.get("template_name")):
                template = await template_service.get_template_by_code(
                    tenant_id,
                    result.get("document_type") or result.get("template_name")
                )

            if template:
                await push_to_feishu(
                    template=template,
                    extraction_data=result.get("extraction_data", {}),
                    display_name=display_name,
                    document_id=document_id,
                    source_file_path=source_file_path,
                )
            else:
                logger.info(f"auto_approve 单模板模板未配置飞书，跳过推送: {document_id}")
        except Exception as feishu_error:
            logger.warning(f"auto_approve 单模板飞书推送失败（不影响结果）: {feishu_error}")


async def handle_processing_failure(document_id: str, error_message: str) -> None:
    """处理失败时的统一逻辑"""
    await supabase_service.update_document_status(
        document_id, "failed", error_message=error_message
    )
    logger.error(f"后台处理失败: {document_id} - {error_message}")


async def handle_processing_exception(document_id: str, exception: Exception) -> None:
    """处理异常时的统一逻辑"""
    logger.error(f"后台任务异常: {exception}")
    try:
        await supabase_service.update_document_status(document_id, "failed", str(exception))
    except Exception as update_err:
        logger.warning(f"更新失败状态时出错: {update_err}")
