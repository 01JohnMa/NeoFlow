# api/routes/documents.py
"""文档处理路由"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from typing import Optional
from datetime import datetime
from loguru import logger
import uuid
import os
import aiofiles

from config.settings import settings
from services.supabase_service import supabase_service
from agents.workflow import ocr_workflow

router = APIRouter()


# ============ 辅助函数 ============

async def save_upload_file(file: UploadFile, destination: str) -> int:
    """保存上传的文件"""
    async with aiofiles.open(destination, 'wb') as out_file:
        content = await file.read()
        await out_file.write(content)
        return len(content)


def validate_file_extension(filename: str) -> bool:
    """验证文件扩展名"""
    ext = os.path.splitext(filename)[1].lower()
    return ext in settings.allowed_extensions_list


# ============ API路由 ============

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None)
):
    """
    上传文档
    
    - **file**: 上传的文件（PDF或图像）
    - **user_id**: 用户ID（可选）
    - **metadata**: 额外的元数据（JSON字符串，可选）
    """
    try:
        # 验证文件类型
        if not validate_file_extension(file.filename):
            raise HTTPException(
                status_code=400, 
                detail=f"不支持的文件类型。支持: {settings.ALLOWED_EXTENSIONS}"
            )
        
        # 生成唯一ID和文件路径
        document_id = str(uuid.uuid4())
        file_ext = os.path.splitext(file.filename)[1]
        stored_filename = f"{document_id}{file_ext}"
        file_path = os.path.join(settings.UPLOAD_FOLDER, stored_filename)
        
        # 保存文件
        file_size = await save_upload_file(file, file_path)
        
        # 验证文件大小
        if file_size > settings.MAX_FILE_SIZE:
            os.remove(file_path)
            raise HTTPException(
                status_code=400, 
                detail=f"文件太大。最大: {settings.MAX_FILE_SIZE / 1024 / 1024:.1f}MB"
            )
        
        # 创建数据库记录
        document_data = {
            "id": document_id,
            "user_id": user_id,
            "file_name": stored_filename,
            "original_file_name": file.filename,
            "file_path": file_path,
            "file_size": file_size,
            "file_type": file.content_type,
            "file_extension": file_ext,
            "mime_type": file.content_type,
            "status": "uploaded"
        }
        
        try:
            await supabase_service.create_document(document_data)
            logger.info(f"文档已保存到数据库: {document_id}")
        except Exception as e:
            logger.warning(f"数据库保存失败（文件已保存）: {e}")
        
        return {
            "document_id": document_id,
            "status": "uploaded",
            "message": "文档上传成功",
            "file_name": file.filename,
            "file_size": file_size,
            "file_path": file_path,
            "created_at": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@router.post("/{document_id}/process")
async def process_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    sync: bool = False
):
    """
    处理文档
    
    - **document_id**: 文档ID
    - **sync**: 是否同步处理（默认异步后台处理）
    """
    try:
        # 获取文档信息
        document = await supabase_service.get_document(document_id)
        
        if not document:
            # 尝试从本地查找
            for file in os.listdir(settings.UPLOAD_FOLDER):
                if file.startswith(document_id):
                    file_path = os.path.join(settings.UPLOAD_FOLDER, file)
                    break
            else:
                raise HTTPException(status_code=404, detail="文档不存在")
        else:
            file_path = document.get("file_path")
            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail="文件不存在")
        
        if sync:
            # 同步处理
            result = await ocr_workflow.process(document_id, file_path)
            
            # 保存结果到数据库
            if result["success"] and result.get("extraction_data"):
                try:
                    await supabase_service.save_extraction_result(
                        document_id=document_id,
                        document_type=result["document_type"],
                        extraction_data=result["extraction_data"]
                    )
                    await supabase_service.update_document_status(document_id, "completed")
                except Exception as e:
                    logger.warning(f"保存结果到数据库失败: {e}")
            
            return result
        else:
            # 异步处理
            background_tasks.add_task(
                process_document_task,
                document_id=document_id,
                file_path=file_path
            )
            
            # 更新状态
            try:
                await supabase_service.update_document_status(document_id, "processing")
            except:
                pass
            
            return {
                "document_id": document_id,
                "status": "processing",
                "message": "文档处理已开始（后台任务）",
                "estimated_time": "30-60秒"
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理失败: {e}")
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


async def process_document_task(document_id: str, file_path: str):
    """后台处理任务"""
    try:
        logger.info(f"开始后台处理: {document_id}")
        
        result = await ocr_workflow.process(document_id, file_path)
        
        if result["success"] and result.get("extraction_data"):
            await supabase_service.save_extraction_result(
                document_id=document_id,
                document_type=result["document_type"],
                extraction_data=result["extraction_data"]
            )
            await supabase_service.update_document_status(document_id, "completed")
            logger.info(f"后台处理完成: {document_id}")
        else:
            await supabase_service.update_document_status(
                document_id, "failed", 
                error_message=result.get("error", "处理失败")
            )
            logger.error(f"后台处理失败: {document_id} - {result.get('error')}")
            
    except Exception as e:
        logger.error(f"后台任务异常: {e}")
        try:
            await supabase_service.update_document_status(document_id, "failed", str(e))
        except:
            pass


@router.get("/{document_id}/status")
async def get_document_status(document_id: str):
    """获取文档处理状态"""
    try:
        document = await supabase_service.get_document(document_id)
        
        if not document:
            raise HTTPException(status_code=404, detail="文档不存在")
        
        return {
            "document_id": document_id,
            "status": document.get("status", "unknown"),
            "document_type": document.get("document_type"),
            "error_message": document.get("error_message"),
            "created_at": document.get("created_at"),
            "updated_at": document.get("updated_at"),
            "processed_at": document.get("processed_at")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")


@router.get("/{document_id}/result")
async def get_extraction_result(document_id: str):
    """获取提取结果"""
    try:
        document = await supabase_service.get_document(document_id)
        
        if not document:
            raise HTTPException(status_code=404, detail="文档不存在")
        
        document_type = document.get("document_type")
        if not document_type:
            raise HTTPException(status_code=404, detail="文档尚未处理完成")
        
        result = await supabase_service.get_extraction_result(document_id, document_type)
        
        if not result:
            raise HTTPException(status_code=404, detail="提取结果不存在")
        
        return {
            "document_id": document_id,
            "document_type": document_type,
            "extraction_data": result,
            "ocr_text": document.get("ocr_text", "")[:1000],
            "ocr_confidence": document.get("ocr_confidence"),
            "created_at": result.get("created_at"),
            "is_validated": result.get("is_validated", False)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取结果失败: {str(e)}")


@router.get("/{document_id}/download")
async def download_document(document_id: str):
    """下载原始文档"""
    try:
        document = await supabase_service.get_document(document_id)
        
        if not document:
            # 尝试从本地查找
            for file in os.listdir(settings.UPLOAD_FOLDER):
                if file.startswith(document_id):
                    file_path = os.path.join(settings.UPLOAD_FOLDER, file)
                    return FileResponse(
                        path=file_path,
                        filename=file,
                        media_type="application/octet-stream"
                    )
            raise HTTPException(status_code=404, detail="文档不存在")
        
        file_path = document.get("file_path")
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="文件不存在")
        
        return FileResponse(
            path=file_path,
            filename=document.get("original_file_name", document.get("file_name")),
            media_type=document.get("mime_type", "application/octet-stream")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")


@router.get("/")
async def list_documents(
    page: int = 1,
    limit: int = 20,
    status: Optional[str] = None,
    document_type: Optional[str] = None
):
    """列出文档"""
    try:
        documents = await supabase_service.list_documents(
            page=page,
            limit=limit,
            status=status,
            document_type=document_type
        )
        
        total = await supabase_service.count_documents(
            status=status,
            document_type=document_type
        )
        
        return {
            "items": documents,
            "total": total,
            "page": page,
            "limit": limit,
            "has_more": (page * limit) < total
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.delete("/{document_id}")
async def delete_document(document_id: str):
    """删除文档"""
    try:
        document = await supabase_service.get_document(document_id)
        
        if document:
            # 删除文件
            file_path = document.get("file_path")
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
            
            # 删除数据库记录
            await supabase_service.delete_document(document_id)
        else:
            # 尝试从本地删除
            for file in os.listdir(settings.UPLOAD_FOLDER):
                if file.startswith(document_id):
                    os.remove(os.path.join(settings.UPLOAD_FOLDER, file))
                    break
        
        return {
            "document_id": document_id,
            "message": "文档删除成功"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.post("/process-text")
async def process_text_directly(
    text: str = Form(...),
    document_id: Optional[str] = Form(None)
):
    """
    直接处理OCR文本（跳过OCR步骤）
    
    用于已经有OCR结果的场景
    """
    try:
        if not text.strip():
            raise HTTPException(status_code=400, detail="文本不能为空")
        
        doc_id = document_id or str(uuid.uuid4())
        
        result = await ocr_workflow.process_with_text(doc_id, text)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")

