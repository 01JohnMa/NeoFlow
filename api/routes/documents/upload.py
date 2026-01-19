# api/routes/documents/upload.py
"""文档路由 - 上传相关端点"""

from fastapi import APIRouter, UploadFile, File, Form, Depends
from typing import Optional
from datetime import datetime
from loguru import logger
import uuid
import os

from config.settings import settings
from services.supabase_service import supabase_service
from api.dependencies.auth import get_current_user, CurrentUser
from api.exceptions import FileTypeError, FileSizeError, ProcessingError
from .helpers import save_upload_file, validate_file_extension

router = APIRouter()


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(None),
    user: CurrentUser = Depends(get_current_user)
):
    """
    上传文档（需要登录）
    
    - **file**: 上传的文件（PDF或图像）
    - **metadata**: 额外的元数据（JSON字符串，可选）
    - 用户ID从JWT token中自动提取
    """
    try:
        # 验证文件类型
        if not validate_file_extension(file.filename):
            raise FileTypeError(settings.ALLOWED_EXTENSIONS)
        
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
            raise FileSizeError(settings.MAX_FILE_SIZE / 1024 / 1024)
        
        # 创建数据库记录
        document_data = {
            "id": document_id,
            "user_id": user.user_id,
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
            logger.info(f"文档已保存到数据库: {document_id}, 用户: {user.user_id}")
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
        
    except (FileTypeError, FileSizeError):
        raise
    except Exception as e:
        logger.error(f"上传失败: {e}")
        raise ProcessingError(f"上传失败: {str(e)}")
