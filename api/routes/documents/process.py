# api/routes/documents/process.py
"""文档路由 - 处理相关端点"""

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Depends
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel
from loguru import logger
import uuid
import os

from config.settings import settings
from services.supabase_service import supabase_service
from services.template_service import template_service
from services.feishu_service import feishu_service
from agents.workflow import ocr_workflow
from api.exceptions import DocumentNotFoundError, FileNotFoundError, ProcessingError
from api.dependencies.auth import get_current_user, CurrentUser


# ============ 请求模型 ============

class MergeFileInfo(BaseModel):
    """Merge 模式文件信息"""
    file_path: str
    doc_type: str  # 如 "积分球" 或 "光分布"


class ProcessWithTemplateRequest(BaseModel):
    """模板化处理请求"""
    template_id: str
    sync: bool = False


class ProcessMergeRequest(BaseModel):
    """合并模式处理请求"""
    template_id: str
    files: List[MergeFileInfo]

router = APIRouter()


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
                raise DocumentNotFoundError(document_id)
        else:
            file_path = document.get("file_path")
            if not os.path.exists(file_path):
                raise FileNotFoundError(file_path)
        
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
                    # 生成规范化显示名称
                    display_name = supabase_service.generate_display_name(
                        document_type=result["document_type"],
                        extraction_data=result["extraction_data"]
                    )
                    await supabase_service.update_document(document_id, {
                        "status": "pending_review",
                        "display_name": display_name,
                        "error_message": None
                    })
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
        
    except (DocumentNotFoundError, FileNotFoundError):
        raise
    except Exception as e:
        logger.error(f"处理失败: {e}")
        raise ProcessingError(f"处理失败: {str(e)}")


async def process_document_task(document_id: str, file_path: str):
    """后台处理任务"""
    try:
        logger.info(f"开始后台处理: {document_id}")
        
        result = await ocr_workflow.process(document_id, file_path)
        
        if result["success"] and result.get("extraction_data"):
            # 第一步：保存提取结果到对应的表
            await supabase_service.save_extraction_result(
                document_id=document_id,
                document_type=result["document_type"],
                extraction_data=result["extraction_data"]
            )
            logger.info(f"提取结果已保存: {document_id}")
            
            # 生成规范化显示名称
            display_name = supabase_service.generate_display_name(
                document_type=result["document_type"],
                extraction_data=result["extraction_data"]
            )
            
            # 第二步：更新文档状态为 pending_review（待人工审核）
            await supabase_service.update_document(document_id, {
                "status": "pending_review",
                "document_type": result["document_type"],
                "display_name": display_name,
                "ocr_text": result.get("ocr_text", ""),
                "ocr_confidence": result.get("ocr_confidence"),
                "processed_at": datetime.now().isoformat(),
                "error_message": None
            })
            logger.info(f"后台处理完成: {document_id}, 显示名称: {display_name}")
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
        raise ProcessingError(f"处理失败: {str(e)}")


# ============ 模板化处理端点 ============

@router.post("/{document_id}/process-with-template")
async def process_document_with_template(
    document_id: str,
    request: ProcessWithTemplateRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user)
):
    """
    使用指定模板处理文档
    
    - **document_id**: 文档ID
    - **template_id**: 模板ID
    - **sync**: 是否同步处理（默认异步后台处理）
    """
    try:
        # 检查用户租户
        if not user.tenant_id:
            raise HTTPException(status_code=400, detail="请先选择所属部门")
        
        # 获取文档信息
        document = await supabase_service.get_document(document_id)
        if not document:
            raise DocumentNotFoundError(document_id)
        
        file_path = document.get("file_path")
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(file_path or "未知路径")
        
        # 获取模板信息
        template = await template_service.get_template(request.template_id)
        if not template:
            raise HTTPException(status_code=404, detail="模板不存在")
        
        # 检查模板是否属于用户的租户
        if template.get("tenant_id") != user.tenant_id and not user.is_super_admin():
            raise HTTPException(status_code=403, detail="无权使用此模板")
        
        if request.sync:
            # 同步处理
            result = await ocr_workflow.process_with_template(
                document_id=document_id,
                file_path=file_path,
                template_id=request.template_id,
                tenant_id=user.tenant_id
            )
            
            # 保存结果
            if result["success"] and result.get("extraction_data"):
                await _save_template_extraction_result(
                    document_id=document_id,
                    template=template,
                    result=result,
                    user=user
                )
            
            return result
        else:
            # 异步处理
            background_tasks.add_task(
                process_document_with_template_task,
                document_id=document_id,
                file_path=file_path,
                template_id=request.template_id,
                tenant_id=user.tenant_id
            )
            
            await supabase_service.update_document_status(document_id, "processing")
            
            return {
                "document_id": document_id,
                "template_id": request.template_id,
                "status": "processing",
                "message": "文档处理已开始（后台任务）"
            }
        
    except (DocumentNotFoundError, FileNotFoundError, HTTPException):
        raise
    except Exception as e:
        logger.error(f"模板化处理失败: {e}")
        raise ProcessingError(f"处理失败: {str(e)}")


async def process_document_with_template_task(
    document_id: str, 
    file_path: str,
    template_id: str,
    tenant_id: str
):
    """模板化处理后台任务"""
    try:
        logger.info(f"开始模板化后台处理: {document_id}, 模板: {template_id}")
        
        result = await ocr_workflow.process_with_template(
            document_id=document_id,
            file_path=file_path,
            template_id=template_id,
            tenant_id=tenant_id
        )
        
        if result["success"] and result.get("extraction_data"):
            # 获取模板信息
            template = await template_service.get_template_with_details(template_id)
            
            # 更新文档
            await supabase_service.update_document(document_id, {
                "status": "pending_review",
                "document_type": result.get("template_name"),
                "template_id": template_id,
                "tenant_id": tenant_id,
                "ocr_text": result.get("ocr_text", ""),
                "ocr_confidence": result.get("ocr_confidence"),
                "processed_at": datetime.now().isoformat(),
                "error_message": None
            })
            
            # 保存提取结果
            await supabase_service.save_extraction_result(
                document_id=document_id,
                document_type=result.get("template_name", "未知"),
                extraction_data=result["extraction_data"]
            )
            
            logger.info(f"模板化后台处理完成: {document_id}")
        else:
            await supabase_service.update_document_status(
                document_id, "failed",
                error_message=result.get("error", "处理失败")
            )
            logger.error(f"模板化后台处理失败: {document_id}")
            
    except Exception as e:
        logger.error(f"模板化后台任务异常: {e}")
        try:
            await supabase_service.update_document_status(document_id, "failed", str(e))
        except:
            pass


@router.post("/process-merge")
async def process_merge_documents(
    request: ProcessMergeRequest,
    user: CurrentUser = Depends(get_current_user)
):
    """
    合并模式处理：多份文档分别提取后合并
    
    用于照明事业部场景：上传积分球+光分布文档，分别提取后合并结果
    
    - **template_id**: 合并模板ID（process_mode='merge'）
    - **files**: 文件列表，每项包含 file_path 和 doc_type
    """
    try:
        if not user.tenant_id:
            raise HTTPException(status_code=400, detail="请先选择所属部门")
        
        if not request.files:
            raise HTTPException(status_code=400, detail="请提供至少一个文件")
        
        # 获取模板
        template = await template_service.get_template(request.template_id)
        if not template:
            raise HTTPException(status_code=404, detail="模板不存在")
        
        if template.get("process_mode") != "merge":
            raise HTTPException(status_code=400, detail="此模板不支持合并模式")
        
        if template.get("tenant_id") != user.tenant_id and not user.is_super_admin():
            raise HTTPException(status_code=403, detail="无权使用此模板")
        
        # 验证文件存在
        files = []
        for file_info in request.files:
            if not os.path.exists(file_info.file_path):
                raise FileNotFoundError(file_info.file_path)
            files.append({
                "file_path": file_info.file_path,
                "doc_type": file_info.doc_type
            })
        
        # 生成文档 ID
        document_id = str(uuid.uuid4())
        
        # 执行合并处理
        result = await ocr_workflow.process_merge(
            document_id=document_id,
            files=files,
            template_id=request.template_id,
            tenant_id=user.tenant_id
        )
        
        return result
        
    except (FileNotFoundError, HTTPException):
        raise
    except Exception as e:
        logger.error(f"合并处理失败: {e}")
        raise ProcessingError(f"处理失败: {str(e)}")


async def _save_template_extraction_result(
    document_id: str,
    template: dict,
    result: dict,
    user: CurrentUser
):
    """保存模板化提取结果"""
    try:
        # 更新文档状态
        await supabase_service.update_document(document_id, {
            "status": "pending_review",
            "document_type": result.get("template_name"),
            "template_id": template.get("id"),
            "tenant_id": user.tenant_id,
            "ocr_text": result.get("ocr_text", ""),
            "ocr_confidence": result.get("ocr_confidence"),
            "processed_at": datetime.now().isoformat(),
            "error_message": None
        })
        
        # 保存提取结果
        await supabase_service.save_extraction_result(
            document_id=document_id,
            document_type=result.get("template_name", "未知"),
            extraction_data=result["extraction_data"]
        )
        
    except Exception as e:
        logger.error(f"保存模板提取结果失败: {e}")
