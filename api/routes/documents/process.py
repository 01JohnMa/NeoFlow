# api/routes/documents/process.py
"""文档路由 - 处理相关端点"""

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Depends
from fastapi.responses import JSONResponse
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel
from loguru import logger
import asyncio
import uuid
import os

from config.settings import settings
from services.supabase_service import supabase_service
from services.template_service import template_service
from agents.workflow import ocr_workflow
from api.exceptions import DocumentNotFoundError, FileNotFoundError, ProcessingError, AppException
from api.dependencies.auth import get_current_user, CurrentUser
from api.jobs import create_job, update_job, get_job
from .helpers import push_to_feishu, handle_processing_success, handle_processing_failure, handle_processing_exception


# ============ 请求模型 ============

class MergeFileInfo(BaseModel):
    """Merge 模式文件信息"""
    file_path: str


class ProcessWithTemplateRequest(BaseModel):
    """模板化处理请求"""
    template_id: str
    sync: bool = False


class ProcessMergeRequest(BaseModel):
    """合并模式处理请求"""
    sub_template_a_id: str
    sub_template_b_id: str
    files: List[MergeFileInfo]

router = APIRouter()


# ============ 后台任务辅助函数（委托到 helpers）============

_handle_processing_success = handle_processing_success
_handle_processing_failure = handle_processing_failure
_handle_processing_exception = handle_processing_exception


@router.post("/{document_id}/process")
async def process_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    sync: bool = False,
    user: CurrentUser = Depends(get_current_user)
):
    """
    处理文档（需要登录）
    
    - **document_id**: 文档ID
    - **sync**: 是否同步处理（默认异步后台处理）
    
    如果文档关联了 template_id，将使用模板化处理流程；
    否则使用原有的自动分类处理流程（质量管理中心）。
    """
    try:
        # 检查用户是否已关联租户
        if not user.tenant_id:
            raise ProcessingError("请先在个人设置中选择所属部门后再处理文档")
        
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
        
        # 检查文档是否关联了模板
        template_id = document.get("template_id") if document else None
        # 优先使用当前用户的 tenant_id（支持重新处理时使用更新后的租户）
        tenant_id = user.tenant_id or document.get("tenant_id")
        
        # 如果文档的 tenant_id 为空，更新为当前用户的 tenant_id
        if document and not document.get("tenant_id") and user.tenant_id:
            await supabase_service.update_document(document_id, {"tenant_id": user.tenant_id})
        
        if sync:
            # 同步处理
            if template_id:
                # 使用模板化处理
                result = await ocr_workflow.process_with_template(
                    document_id=document_id,
                    file_path=file_path,
                    template_id=template_id,
                    tenant_id=tenant_id
                )
            else:
                # 原有流程（质量管理中心分类）
                result = await ocr_workflow.process(document_id, file_path, tenant_id=tenant_id)
            
            # 保存结果到数据库
            if result["success"] and result.get("extraction_data"):
                try:
                    auto_approve = False
                    template = None
                    if template_id:
                        template = await template_service.get_template(template_id)
                    elif tenant_id and result.get("document_type"):
                        template = await template_service.get_template_by_code(tenant_id, result.get("document_type"))
                    if template:
                        auto_approve = bool(template.get("auto_approve", False))

                    await _handle_processing_success(
                        document_id=document_id,
                        result=result,
                        template_id=template_id or (template.get("id") if template else None),
                        tenant_id=tenant_id,
                        generate_display_name=True,
                        auto_approve=auto_approve,
                        source_file_path=file_path
                    )
                except Exception as e:
                    logger.warning(f"保存结果到数据库失败: {e}")
            
            return result
        else:
            # 异步处理
            background_tasks.add_task(
                process_document_task,
                document_id=document_id,
                file_path=file_path,
                template_id=template_id,
                tenant_id=tenant_id
            )
            
            # 更新状态
            try:
                await supabase_service.update_document_status(document_id, "processing")
            except Exception as status_err:
                logger.warning(f"更新处理状态失败: {status_err}")
            
            return {
                "document_id": document_id,
                "status": "processing",
                "message": "文档处理已开始（后台任务）",
                "estimated_time": "30-60秒",
                "use_template": template_id is not None
            }
        
    except (DocumentNotFoundError, FileNotFoundError):
        raise
    except Exception as e:
        logger.error(f"处理失败: {e}")
        raise ProcessingError(f"处理失败: {str(e)}")


async def process_document_task(
    document_id: str, 
    file_path: str,
    template_id: Optional[str] = None,
    tenant_id: Optional[str] = None
):
    """后台处理任务
    
    Args:
        document_id: 文档ID
        file_path: 文件路径
        template_id: 模板ID（可选，有则使用模板化处理）
        tenant_id: 租户ID（可选）
    """
    try:
        logger.info(f"开始后台处理: {document_id}, 模板: {template_id or '无(自动分类)'}")
        
        # 根据是否有模板选择处理方式
        if template_id:
            result = await ocr_workflow.process_with_template(
                document_id=document_id,
                file_path=file_path,
                template_id=template_id,
                tenant_id=tenant_id
            )
        else:
            result = await ocr_workflow.process(document_id, file_path, tenant_id=tenant_id)
        
        if result["success"] and result.get("extraction_data"):
            auto_approve = False
            template = None
            if template_id:
                template = await template_service.get_template(template_id)
            elif tenant_id and result.get("document_type"):
                template = await template_service.get_template_by_code(tenant_id, result.get("document_type"))
            if template:
                auto_approve = bool(template.get("auto_approve", False))

            await _handle_processing_success(
                document_id=document_id,
                result=result,
                template_id=template_id or (template.get("id") if template else None),
                tenant_id=tenant_id,
                generate_display_name=True,
                auto_approve=auto_approve,
                source_file_path=file_path
            )
        else:
            await _handle_processing_failure(
                document_id, 
                result.get("error", "处理失败")
            )
            
    except Exception as e:
        await _handle_processing_exception(document_id, e)


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
        
        auto_approve = bool(template.get("auto_approve", False))

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
                    user=user,
                    file_path=file_path,
                    auto_approve=auto_approve
                )
            
            return result
        else:
            # 异步处理
            background_tasks.add_task(
                process_document_with_template_task,
                document_id=document_id,
                file_path=file_path,
                template_id=request.template_id,
                tenant_id=user.tenant_id,
                auto_approve=auto_approve
            )
            
            await supabase_service.update_document_status(document_id, "processing")
            
            return JSONResponse(status_code=202, content={
                "document_id": document_id,
                "template_id": request.template_id,
                "status": "processing",
                "message": "文档处理已开始（后台任务）"
            })
        
    except (DocumentNotFoundError, FileNotFoundError, HTTPException):
        raise
    except Exception as e:
        logger.error(f"模板化处理失败: {e}")
        raise ProcessingError(f"处理失败: {str(e)}")


async def process_document_with_template_task(
    document_id: str, 
    file_path: str,
    template_id: str,
    tenant_id: str,
    auto_approve: bool = False
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
            await _handle_processing_success(
                document_id=document_id,
                result=result,
                template_id=template_id,
                tenant_id=tenant_id,
                generate_display_name=False,  # 模板化处理不生成显示名称
                auto_approve=auto_approve,
                source_file_path=file_path
            )
        else:
            await _handle_processing_failure(
                document_id, 
                result.get("error", "处理失败")
            )
            
    except Exception as e:
        await _handle_processing_exception(document_id, e)


@router.post("/process-merge")
async def process_merge_documents(
    request: ProcessMergeRequest,
    user: CurrentUser = Depends(get_current_user)
):
    """
    合并模式处理（异步）：立即返回 job_id，后台执行 OCR + LLM + 保存

    前端拿到 job_id 后轮询 GET /documents/jobs/{job_id} 获取进度。

    - **sub_template_a_id**: 文件A的子模板ID
    - **sub_template_b_id**: 文件B的子模板ID
    - **files**: 文件列表，files[0] 对应 sub_template_a，files[1] 对应 sub_template_b
    """
    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="请先选择所属部门")

    if not request.files:
        raise HTTPException(status_code=400, detail="请提供至少一个文件")

    # 前置校验
    template_a = await template_service.get_template(request.sub_template_a_id)
    if not template_a:
        raise HTTPException(status_code=404, detail="子模板 A 不存在")
    template_b = await template_service.get_template(request.sub_template_b_id)
    if not template_b:
        raise HTTPException(status_code=404, detail="子模板 B 不存在")

    if template_a.get("tenant_id") != user.tenant_id and not user.is_super_admin():
        raise HTTPException(status_code=403, detail="无权使用子模板 A")

    # 验证文件存在并收集原始文档 ID
    files = []
    source_doc_ids = []
    for file_info in request.files:
        if not os.path.exists(file_info.file_path):
            raise HTTPException(status_code=404, detail=f"文件不存在: {file_info.file_path}")
        files.append({"file_path": file_info.file_path})
        source_doc = await supabase_service.get_document_by_file_path(file_info.file_path)
        if source_doc:
            source_doc_ids.append(source_doc["id"])

    # 创建 Job 并在后台运行
    job_id = create_job()
    asyncio.create_task(
        _run_merge_job(
            job_id, files, source_doc_ids,
            request.sub_template_a_id, request.sub_template_b_id,
            template_a, user,
        )
    )
    logger.info(f"合并任务已提交: job_id={job_id}, 文件数={len(files)}")

    return JSONResponse(status_code=202, content={"job_id": job_id, "status": "pending"})


@router.get("/jobs/{job_id}")
async def get_merge_job_status(
    job_id: str,
    user: CurrentUser = Depends(get_current_user)
):
    """查询合并任务状态（前端轮询用）

    Returns:
        {
            "job_id": "...",
            "status": "pending|processing|completed|failed",
            "stage": "pending|ocr|llm|saving|completed|failed",
            "progress": 0~100,
            "document_ids": [...],   # completed 时填入
            "error": "..."           # failed 时填入
        }
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return job


async def _run_merge_job(
    job_id: str,
    files: list,
    source_doc_ids: list,
    sub_template_a_id: str,
    sub_template_b_id: str,
    template_a: dict,
    user: CurrentUser,
):
    """后台合并任务：OCR → LLM → 推送或存储待审核"""
    created_doc_ids: list = []
    try:
        template_name = template_a.get("name", "综合报告")
        auto_approve = template_a.get("auto_approve", False)

        # 阶段1：OCR + LLM 提取
        update_job(job_id, "ocr")
        result = await ocr_workflow.process_merge(
            document_id=str(uuid.uuid4()),
            files=files,
            sub_template_a_id=sub_template_a_id,
            sub_template_b_id=sub_template_b_id,
            tenant_id=user.tenant_id,
        )

        if not result.get("success"):
            error_msg = result.get("error", "合并处理失败")
            logger.error(f"[job={job_id}] 合并处理失败: {error_msg}")
            update_job(job_id, "failed", error=error_msg)
            return

        extraction_results = result.get("extraction_results", [])
        if not extraction_results:
            update_job(job_id, "failed", error="未提取到有效字段，请检查模板与文档类型")
            return

        sample_count = len(extraction_results)
        logger.info(f"[job={job_id}] 提取完成，共 {sample_count} 个样品")

        update_job(job_id, "saving")

        sub_results = result.get("sub_results", {})
        results_a = sub_results.get("results_a", [])
        result_b = sub_results.get("result_b")

        # 获取子模板详情（用于 code 字段）
        sub_template_a = await template_service.get_template(sub_template_a_id)
        sub_template_b = await template_service.get_template(sub_template_b_id)

        doc_b_id = source_doc_ids[1] if len(source_doc_ids) > 1 else None
        doc_a_id_original = source_doc_ids[0] if source_doc_ids else None

        if auto_approve:
            for sample_result in extraction_results:
                sample_index = sample_result.get("sample_index", 1)
                sample_data = sample_result.get("data", {})
                if not sample_data:
                    continue
                display_name = supabase_service.generate_display_name(
                    document_type=template_name, extraction_data=sample_data,
                )
                if sample_count > 1:
                    display_name = f"{display_name}_样品{sample_index}"
                try:
                    await push_to_feishu(
                        template=template_a,
                        extraction_data=sample_data,
                        display_name=display_name,
                        document_id=f"merge-{job_id}-{sample_index}",
                        log_prefix=f"[job={job_id}] 样品{sample_index} ",
                    )
                except Exception as feishu_error:
                    logger.warning(f"[job={job_id}] 飞书推送失败（不影响结果）: {feishu_error}")

            update_job(job_id, "completed", document_ids=source_doc_ids)
            logger.info(f"[job={job_id}] auto_approve 合并推送完成")
            return

        # 非 auto_approve：各文档只存自己的原始字段，记录配对关系
        first_doc_a_id = None
        sub_a_code = sub_template_a.get("code", "") if sub_template_a else ""
        for i, result_a_data in enumerate(results_a):
            sample_index = i + 1
            if not result_a_data:
                continue

            if len(results_a) <= 1 and doc_a_id_original:
                doc_a_id = doc_a_id_original
            else:
                doc_a_id = str(uuid.uuid4())
                created_doc_ids.append(doc_a_id)
                display_name = supabase_service.generate_display_name(
                    document_type=template_name, extraction_data=result_a_data,
                )
                await supabase_service.create_document({
                    "id": doc_a_id,
                    "user_id": user.user_id,
                    "tenant_id": user.tenant_id,
                    "template_id": sub_template_a_id,
                    "document_type": sub_a_code,
                    "status": "pending_review",
                    "display_name": f"{display_name}_样品{sample_index}",
                    "original_file_name": f"{display_name}_样品{sample_index}",
                    "file_name": f"sample_{doc_a_id}",
                    "file_path": "",
                    "source_document_ids": [doc_a_id_original] if doc_a_id_original else [],
                    "processed_at": datetime.now().isoformat(),
                })

            if first_doc_a_id is None:
                first_doc_a_id = doc_a_id

            await supabase_service.save_extraction_result(
                document_id=doc_a_id,
                document_type=sub_a_code,
                extraction_data=result_a_data,
                template_id=sub_template_a_id,
            )
            await supabase_service.update_document(doc_a_id, {
                "status": "pending_review",
                "paired_document_id": doc_b_id,
                "merge_template_id": sub_template_a_id,
            })
            logger.info(f"[job={job_id}] 样品{sample_index} 存入文档A: {doc_a_id}")

        if result_b and doc_b_id:
            sub_b_code = sub_template_b.get("code", "") if sub_template_b else ""
            await supabase_service.save_extraction_result(
                document_id=doc_b_id,
                document_type=sub_b_code,
                extraction_data=result_b,
                template_id=sub_template_b_id,
            )
            await supabase_service.update_document(doc_b_id, {
                "status": "pending_review",
                "paired_document_id": first_doc_a_id,
                "merge_template_id": sub_template_a_id,
            })
            logger.info(f"[job={job_id}] 文档B 存储完成: {doc_b_id}")

        all_doc_ids = ([doc_a_id_original] if doc_a_id_original else []) + created_doc_ids + ([doc_b_id] if doc_b_id else [])
        update_job(job_id, "completed", document_ids=all_doc_ids)
        logger.info(f"[job={job_id}] 任务完成，待审核文档: {all_doc_ids}")

    except Exception as e:
        logger.error(f"[job={job_id}] 后台任务异常: {e}")
        for doc_id in created_doc_ids:
            try:
                await supabase_service.update_document_status(doc_id, "failed", str(e))
            except Exception:
                pass
        update_job(job_id, "failed", error=str(e))


async def _save_template_extraction_result(
    document_id: str,
    template: dict,
    result: dict,
    user: CurrentUser,
    file_path: Optional[str] = None,
    auto_approve: bool = False,
):
    """保存模板化提取结果"""
    try:
        await _handle_processing_success(
            document_id=document_id,
            result=result,
            template_id=template.get("id"),
            tenant_id=user.tenant_id,
            generate_display_name=False,
            auto_approve=auto_approve,
            source_file_path=file_path
        )
    except Exception as e:
        logger.error(f"保存模板提取结果失败: {e}")
