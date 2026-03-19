# api/routes/documents/review.py
"""文档路由 - 审核相关端点"""

from fastapi import APIRouter, Depends
from datetime import datetime
from loguru import logger

from services.supabase_service import supabase_service
from services.template_service import template_service
from api.dependencies.auth import get_current_user, CurrentUser
from api.exceptions import (
    DocumentNotFoundError, 
    DocumentTypeError, 
    ValidationError,
    ProcessingError
)
from .schemas import ValidateRequest, RejectRequest, RenameRequest
from .helpers import normalize_review_value, parse_allowed_values, push_to_feishu
from .query import _check_document_access

router = APIRouter()


def _validate_review_rules(template: dict, data: dict) -> None:
    fields = template.get("template_fields") or []
    for field in fields:
        if not field or not field.get("review_enforced"):
            continue
        field_key = field.get("field_key") or ""
        if not field_key:
            continue
        allowed_values = parse_allowed_values(field.get("review_allowed_values"))
        if not allowed_values:
            continue
        current_value = data.get(field_key)
        normalized_current = normalize_review_value(current_value)
        normalized_allowed = {normalize_review_value(v) for v in allowed_values}
        if not normalized_current or normalized_current not in normalized_allowed:
            field_label = field.get("field_label") or field_key
            allowed_text = " / ".join(allowed_values)
            raise ValidationError(f"字段【{field_label}】必须为：{allowed_text}")


@router.put("/{document_id}/validate")
async def validate_document(
    document_id: str,
    request: ValidateRequest,
    user: CurrentUser = Depends(get_current_user)
):
    """
    审核通过并更新字段（需要登录）
    
    - **document_id**: 文档ID
    - **document_type**: 文档类型（检测报告/快递单/抽样单）
    - **data**: 修改后的字段数据
    - **validation_notes**: 审核备注（可选）
    """
    try:
        # 使用 service_role 查询，手动验证权限
        doc_result = supabase_service.client.table("documents").select("*").eq("id", document_id).execute()
        document = doc_result.data[0] if doc_result.data else None
        
        if not document:
            raise DocumentNotFoundError(document_id)
        
        # 验证用户权限（只有文档所有者或管理员可以审核）
        _check_document_access(document, user, document_id)
        
        # 校验强制审核条件（如果配置了字段规则）
        template_id = document.get("template_id")
        tenant_id = document.get("tenant_id")
        template = None
        if template_id:
            template = await template_service.get_template_with_details(template_id)
        elif tenant_id and request.document_type:
            template = await template_service.get_template_by_code(tenant_id, request.document_type)
        if template:
            _validate_review_rules(template, request.data)

        # 准备更新数据
        update_data = {**request.data}
        update_data["is_validated"] = True
        update_data["validated_at"] = datetime.now().isoformat()
        update_data["validated_by"] = user.user_id
        if request.validation_notes:
            update_data["validation_notes"] = request.validation_notes
        
        # 根据文档类型更新对应表（优先用 template_id 查 target_table）
        table_name = supabase_service.resolve_table_name(
            template_id=document.get("template_id"),
            document_type=request.document_type,
        )

        if not table_name:
            raise DocumentTypeError(request.document_type)

        result = supabase_service.client.table(table_name).update(update_data).eq("document_id", document_id).execute()

        if not result.data:
            raise ProcessingError("更新失败")

        # 审核通过后，更新文档主表状态为 completed
        supabase_service.client.table("documents").update({
            "status": "completed"
        }).eq("id", document_id).execute()

        logger.info(f"文档审核通过: {document_id}, 用户: {user.user_id}")

        file_name_for_push = (
            (document.get("display_name") or "").strip()
            or (document.get("original_file_name") or "").strip()
            or (document.get("file_name") or "").strip()
        )

        # 检查是否为 merge 配对文档
        paired_id = document.get("paired_document_id")
        merge_template_id = document.get("merge_template_id")

        if paired_id and merge_template_id:
            # merge 模式：检查配对文档是否也已审核完成
            paired_doc = supabase_service.client.table("documents").select("status, template_id").eq("id", paired_id).execute()
            paired_status = paired_doc.data[0].get("status") if paired_doc.data else None

            if paired_status == "completed":
                # 双方均已审核，从配对文档读对方数据，合并后推飞书
                try:
                    merge_template = await template_service.get_template_with_details(merge_template_id)
                    if merge_template:
                        # 查配对文档的业务表数据
                        paired_template_id = paired_doc.data[0].get("template_id") if paired_doc.data else None
                        paired_doc_type = None
                        if not paired_template_id:
                            paired_doc_full = supabase_service.client.table("documents").select("document_type").eq("id", paired_id).execute()
                            paired_doc_type = paired_doc_full.data[0].get("document_type", "") if paired_doc_full.data else ""
                        paired_table_name = supabase_service.resolve_table_name(
                            template_id=paired_template_id,
                            document_type=paired_doc_type,
                        )

                        paired_data = {}
                        if paired_table_name:
                            paired_result = supabase_service.client.table(paired_table_name).select("*").eq("document_id", paired_id).execute()
                            paired_data = paired_result.data[0] if paired_result.data else {}

                        # 合并当前文档数据 + 配对文档数据，当前文档字段优先
                        merged_data = {**paired_data, **result.data[0]}

                        await push_to_feishu(
                            template=merge_template,
                            extraction_data=merged_data,
                            display_name=file_name_for_push,
                            document_id=document_id,
                            source_file_path=document.get("file_path", ""),
                        )
                        logger.info(f"配对文档均已审核，合并推送完成: {document_id} + {paired_id}")
                    else:
                        logger.warning(f"合并模板不存在: {merge_template_id}，跳过推送")
                except Exception as feishu_error:
                    logger.warning(f"合并推送失败（不影响审核结果）: {feishu_error}")
            else:
                logger.info(f"配对文档 {paired_id} 尚未审核（状态: {paired_status}），等待对方完成后推送")
        else:
            # 普通单文档，走原有推送逻辑
            if template:
                try:
                    await push_to_feishu(
                        template=template,
                        extraction_data=result.data[0],
                        display_name=file_name_for_push,
                        document_id=document_id,
                        source_file_path=document.get("file_path", ""),
                    )
                except Exception as feishu_error:
                    logger.warning(f"飞书推送失败（不影响审核结果）: {feishu_error}")
            else:
                logger.info(f"模板未配置飞书，跳过推送: {document_id}")
        
        return {
            "success": True,
            "message": "审核通过，字段已更新",
            "document_id": document_id
        }
        
    except (DocumentNotFoundError, DocumentTypeError, ProcessingError):
        raise
    except Exception as e:
        logger.error(f"审核失败: {e}")
        raise ProcessingError(f"审核失败: {str(e)}")


@router.put("/{document_id}/rename")
async def rename_document(
    document_id: str,
    request: RenameRequest,
    user: CurrentUser = Depends(get_current_user)
):
    """
    重命名文档（需要登录）
    
    - **document_id**: 文档ID
    - **display_name**: 新的显示名称
    """
    try:
        # 验证名称
        if not request.display_name or not request.display_name.strip():
            raise ValidationError("显示名称不能为空")
        
        if len(request.display_name) > 255:
            raise ValidationError("显示名称不能超过255个字符")
        
        # 使用 service_role 查询，手动验证权限
        doc_result = supabase_service.client.table("documents").select("*").eq("id", document_id).execute()
        document = doc_result.data[0] if doc_result.data else None
        
        if not document:
            raise DocumentNotFoundError(document_id)
        
        # 验证用户权限（只有文档所有者或管理员可以重命名）
        _check_document_access(document, user, document_id)
        
        # 更新显示名称
        supabase_service.client.table("documents").update({
            "display_name": request.display_name.strip()
        }).eq("id", document_id).execute()
        
        logger.info(f"文档重命名: {document_id} -> {request.display_name}")
        
        return {
            "success": True,
            "message": "重命名成功",
            "document_id": document_id,
            "display_name": request.display_name.strip()
        }
        
    except (ValidationError, DocumentNotFoundError):
        raise
    except Exception as e:
        logger.error(f"重命名失败: {e}")
        raise ProcessingError(f"重命名失败: {str(e)}")


@router.put("/{document_id}/reject")
async def reject_document(
    document_id: str,
    request: RejectRequest,
    user: CurrentUser = Depends(get_current_user)
):
    """
    打回文档（需要登录）
    
    - **document_id**: 文档ID
    - **reason**: 打回原因
    """
    try:
        # 使用 service_role 查询，手动验证权限
        doc_result = supabase_service.client.table("documents").select("*").eq("id", document_id).execute()
        document = doc_result.data[0] if doc_result.data else None
        
        if not document:
            raise DocumentNotFoundError(document_id)
        
        # 验证用户权限（只有文档所有者或管理员可以打回）
        _check_document_access(document, user, document_id)
        
        # 更新文档状态为失败
        supabase_service.client.table("documents").update({
            "status": "failed",
            "error_message": f"审核打回: {request.reason}"
        }).eq("id", document_id).execute()
        
        logger.info(f"文档审核打回: {document_id}, 用户: {user.user_id}, 原因: {request.reason}")
        
        return {
            "success": True,
            "message": "文档已打回",
            "document_id": document_id,
            "reason": request.reason
        }
        
    except DocumentNotFoundError:
        raise
    except Exception as e:
        logger.error(f"打回失败: {e}")
        raise ProcessingError(f"打回失败: {str(e)}")
