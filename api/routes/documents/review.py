# api/routes/documents/review.py
"""文档路由 - 重命名"""

from fastapi import APIRouter, Depends
from loguru import logger
import inspect

from services.supabase_service import supabase_service
from api.dependencies.auth import get_current_user, CurrentUser
from api.exceptions import DocumentNotFoundError, ValidationError, ProcessingError
from .schemas import RenameRequest
from .query import _check_document_access

router = APIRouter()


async def _run_supabase(fn):
    runner = getattr(supabase_service, "_run_sync", None)
    if runner is not None and inspect.iscoroutinefunction(runner):
        return await runner(fn)
    return fn()


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
        doc_result = await _run_supabase(
            lambda: supabase_service.client.table("documents").select("*").eq("id", document_id).execute()
        )
        document = doc_result.data[0] if doc_result.data else None
        
        if not document:
            raise DocumentNotFoundError(document_id)
        
        # 验证用户权限（只有文档所有者或管理员可以重命名）
        _check_document_access(document, user, document_id)
        
        # 更新显示名称
        await _run_supabase(
            lambda: supabase_service.client.table("documents").update({
                "display_name": request.display_name.strip()
            }).eq("id", document_id).execute()
        )
        
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
        logger.bind(document_id=document_id).opt(exception=e).error("重命名失败")
        raise ProcessingError(f"重命名失败: {str(e)}")

