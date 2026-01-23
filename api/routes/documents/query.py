# api/routes/documents/query.py
"""文档路由 - 查询相关端点"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional
from loguru import logger
import os

from services.supabase_service import supabase_service
from api.dependencies.auth import get_current_user, get_user_client, CurrentUser
from api.exceptions import DocumentNotFoundError, FileNotFoundError, ProcessingError, AuthenticationError

router = APIRouter()


def _is_auth_error(error: Exception) -> bool:
    """检测是否为认证/授权相关错误（token 过期等）"""
    error_str = str(error).lower()
    auth_keywords = ['jwt', 'token', '401', '502', 'expired', 'invalid', 'unauthorized']
    return any(keyword in error_str for keyword in auth_keywords)


@router.get("/{document_id}/status")
async def get_document_status(
    document_id: str,
    user: CurrentUser = Depends(get_current_user)
):
    """
    获取文档处理状态（需要登录）
    
    RLS 策略确保用户只能访问自己的文档
    """
    try:
        user_client = get_user_client(user)
        
        result = user_client.table("documents").select("*").eq("id", document_id).execute()
        document = result.data[0] if result.data else None
        
        if not document:
            raise DocumentNotFoundError(document_id)
        
        return {
            "document_id": document_id,
            "status": document.get("status", "unknown"),
            "document_type": document.get("document_type"),
            "display_name": document.get("display_name"),
            "original_file_name": document.get("original_file_name"),
            "error_message": document.get("error_message"),
            "created_at": document.get("created_at"),
            "updated_at": document.get("updated_at"),
            "processed_at": document.get("processed_at")
        }
        
    except DocumentNotFoundError:
        raise
    except Exception as e:
        if _is_auth_error(e):
            logger.warning(f"Token 认证失败，需要重新登录: {e}")
            raise AuthenticationError("登录已过期，请重新登录")
        raise ProcessingError(f"获取状态失败: {str(e)}")


@router.get("/{document_id}/result")
async def get_extraction_result(
    document_id: str,
    user: CurrentUser = Depends(get_current_user)
):
    """
    获取提取结果（需要登录）
    
    返回状态码：
    - 200: 成功返回结果
    - 202: 文档正在处理中（前端应继续轮询）
    - 404: 文档不存在或无权访问
    """
    try:
        user_client = get_user_client(user)
        
        doc_result = user_client.table("documents").select("*").eq("id", document_id).execute()
        document = doc_result.data[0] if doc_result.data else None
        
        if not document:
            raise DocumentNotFoundError(document_id)
        
        document_type = document.get("document_type")
        doc_status = document.get("status")
        
        # 表映射关系（使用 supabase_service 的方法）
        table_name = supabase_service.get_table_name(document_type) if document_type else None
        
        # 如果文档正在处理中或尚未有类型
        if not document_type:
            if doc_status in ("uploaded", "processing"):
                return JSONResponse(
                    status_code=202,
                    content={
                        "document_id": document_id,
                        "status": doc_status,
                        "message": "文档正在处理中，请稍后重试"
                    }
                )
            elif doc_status == "completed":
                # 兜底逻辑：尝试从所有结果表查询
                logger.warning(f"文档 {document_id} 状态为 completed 但 document_type 为空")
                
                result = None
                inferred_type = None
                for type_name, tbl_name in [("检测报告", "inspection_reports"), ("快递单", "expresses"), ("抽样单", "sampling_forms")]:
                    try:
                        query_result = user_client.table(tbl_name).select("*").eq("document_id", document_id).execute()
                        if query_result.data:
                            result = query_result.data[0]
                            inferred_type = type_name
                            logger.info(f"从 {tbl_name} 表找到结果，推断文档类型为: {type_name}")
                            break
                    except Exception as e:
                        logger.debug(f"查询 {tbl_name} 失败: {e}")
                        continue
                
                if result and inferred_type:
                    try:
                        supabase_service.client.table("documents").update({"document_type": inferred_type}).eq("id", document_id).execute()
                        logger.info(f"已自动修复文档 {document_id} 的 document_type")
                    except Exception as e:
                        logger.warning(f"自动修复 document_type 失败: {e}")
                    
                    document_type = inferred_type
                else:
                    return JSONResponse(
                        status_code=202,
                        content={
                            "document_id": document_id,
                            "status": "completed",
                            "message": "提取结果正在同步中，请稍后重试"
                        }
                    )
            else:
                raise HTTPException(status_code=404, detail="文档处理未完成或失败")
        else:
            result = None
        
        # 按 document_type 查询
        if result is None:
            table_name = supabase_service.get_table_name(document_type)
            if table_name:
                result_query = user_client.table(table_name).select("*").eq("document_id", document_id).execute()
                result = result_query.data[0] if result_query.data else None
        
        if not result:
            if doc_status == "completed":
                logger.warning(f"文档 {document_id} 状态为 completed 但提取结果尚未查询到")
                return JSONResponse(
                    status_code=202,
                    content={
                        "document_id": document_id,
                        "status": "completed",
                        "message": "提取结果正在同步中，请稍后重试"
                    }
                )
            else:
                raise HTTPException(status_code=404, detail="提取结果不存在")
        
        ocr_text = document.get("ocr_text") or ""
        
        return {
            "document_id": document_id,
            "document_type": document_type,
            "extraction_data": result,
            "ocr_text": ocr_text[:1000] if ocr_text else "",
            "ocr_confidence": document.get("ocr_confidence"),
            "created_at": result.get("created_at"),
            "is_validated": result.get("is_validated", False)
        }
        
    except (DocumentNotFoundError, HTTPException):
        raise
    except Exception as e:
        if _is_auth_error(e):
            logger.warning(f"Token 认证失败，需要重新登录: {e}")
            raise AuthenticationError("登录已过期，请重新登录")
        raise ProcessingError(f"获取结果失败: {str(e)}")


@router.get("/{document_id}/download")
async def download_document(
    document_id: str,
    user: CurrentUser = Depends(get_current_user)
):
    """
    下载原始文档（需要登录）
    """
    try:
        user_client = get_user_client(user)
        
        result = user_client.table("documents").select("*").eq("id", document_id).execute()
        document = result.data[0] if result.data else None
        
        if not document:
            raise DocumentNotFoundError(document_id)
        
        file_path = document.get("file_path")
        if not os.path.exists(file_path):
            raise FileNotFoundError(file_path)
        
        return FileResponse(
            path=file_path,
            filename=document.get("original_file_name", document.get("file_name")),
            media_type=document.get("mime_type", "application/octet-stream")
        )
        
    except (DocumentNotFoundError, FileNotFoundError):
        raise
    except Exception as e:
        if _is_auth_error(e):
            logger.warning(f"Token 认证失败，需要重新登录: {e}")
            raise AuthenticationError("登录已过期，请重新登录")
        raise ProcessingError(f"下载失败: {str(e)}")


@router.get("/")
async def list_documents(
    page: int = 1,
    limit: int = 20,
    status: Optional[str] = None,
    document_type: Optional[str] = None,
    user: CurrentUser = Depends(get_current_user)
):
    """
    列出文档（需要登录）
    
    RLS 策略自动过滤：用户只能看到自己的文档
    """
    try:
        user_client = get_user_client(user)
        
        query = user_client.table("documents").select("*")
        
        if status:
            query = query.eq("status", status)
        if document_type:
            query = query.eq("document_type", document_type)
        
        offset = (page - 1) * limit
        result = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        
        # 统计总数
        count_query = user_client.table("documents").select("id", count="exact")
        if status:
            count_query = count_query.eq("status", status)
        if document_type:
            count_query = count_query.eq("document_type", document_type)
        count_result = count_query.execute()
        
        total = count_result.count or 0
        
        return {
            "items": result.data or [],
            "total": total,
            "page": page,
            "limit": limit,
            "has_more": (page * limit) < total
        }
        
    except Exception as e:
        if _is_auth_error(e):
            logger.warning(f"Token 认证失败，需要重新登录: {e}")
            raise AuthenticationError("登录已过期，请重新登录")
        logger.error(f"查询文档失败: {e}")
        raise ProcessingError(f"查询失败: {str(e)}")


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    user: CurrentUser = Depends(get_current_user)
):
    """
    删除文档（需要登录）
    """
    try:
        user_client = get_user_client(user)
        
        result = user_client.table("documents").select("*").eq("id", document_id).execute()
        document = result.data[0] if result.data else None
        
        if not document:
            raise DocumentNotFoundError(document_id)
        
        # 删除文件
        file_path = document.get("file_path")
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        
        # 删除数据库记录
        user_client.table("documents").delete().eq("id", document_id).execute()
        
        return {
            "document_id": document_id,
            "message": "文档删除成功"
        }
        
    except DocumentNotFoundError:
        raise
    except Exception as e:
        if _is_auth_error(e):
            logger.warning(f"Token 认证失败，需要重新登录: {e}")
            raise AuthenticationError("登录已过期，请重新登录")
        raise ProcessingError(f"删除失败: {str(e)}")
