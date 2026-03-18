# api/routes/documents/batch.py
"""文档路由 - 批量处理端点"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, validator
from typing import List, Optional
from datetime import datetime
from loguru import logger
import asyncio
import uuid
import os

from services.supabase_service import supabase_service
from services.template_service import template_service
from agents.workflow import ocr_workflow
from api.dependencies.auth import get_current_user, CurrentUser
from api.jobs import create_job, update_job, update_batch_item, get_job
from .helpers import (
    handle_processing_success,
    handle_processing_failure,
    push_to_feishu,
)

router = APIRouter()


# ============ 请求模型 ============

class BatchItem(BaseModel):
    type: str  # "single" | "merge"
    document_id: Optional[str] = None
    template_id: str
    # merge 专用
    document_id_a: Optional[str] = None
    doc_type_a: Optional[str] = None
    document_id_b: Optional[str] = None
    doc_type_b: Optional[str] = None


class BatchProcessRequest(BaseModel):
    items: List[BatchItem]

    @validator("items")
    def validate_items_count(cls, v):
        if len(v) == 0:
            raise ValueError("至少需要一个任务项")
        if len(v) > 5:
            raise ValueError("单次批量最多 5 个任务项")
        return v


# ============ 端点 ============

@router.post("/batch-process")
async def batch_process(
    request: BatchProcessRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """批量处理文档（异步），立即返回 job_id"""
    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="请先选择所属部门")

    # 校验每个 item
    for idx, item in enumerate(request.items):
        # 校验模板归属
        tpl = await template_service.get_template(item.template_id)
        if not tpl:
            raise HTTPException(status_code=404, detail=f"任务项 {idx+1}: 模板不存在")
        if tpl.get("tenant_id") != user.tenant_id and not user.is_super_admin():
            raise HTTPException(status_code=403, detail=f"任务项 {idx+1}: 无权使用此模板")

        if item.type == "single":
            if not item.document_id:
                raise HTTPException(status_code=400, detail=f"任务项 {idx+1}: single 类型需要 document_id")
            doc = await supabase_service.get_document(item.document_id)
            if not doc:
                raise HTTPException(status_code=404, detail=f"任务项 {idx+1}: 文档不存在")
        elif item.type == "merge":
            if not all([item.document_id_a, item.document_id_b, item.doc_type_a, item.doc_type_b]):
                raise HTTPException(status_code=400, detail=f"任务项 {idx+1}: merge 类型需要 document_id_a/b 和 doc_type_a/b")
            for did in [item.document_id_a, item.document_id_b]:
                doc = await supabase_service.get_document(did)
                if not doc:
                    raise HTTPException(status_code=404, detail=f"任务项 {idx+1}: 文档 {did} 不存在")
        else:
            raise HTTPException(status_code=400, detail=f"任务项 {idx+1}: type 必须为 single 或 merge")

    # 构建 batch items 结构
    batch_items = []
    for idx, item in enumerate(request.items):
        doc_ids = (
            [item.document_id] if item.type == "single"
            else [item.document_id_a, item.document_id_b]
        )
        batch_items.append({
            "index": idx,
            "type": item.type,
            "document_ids": doc_ids,
            "status": "pending",
        })

    job_id = create_job(batch_items=batch_items)
    asyncio.create_task(_run_batch_job(job_id, request.items, user))
    logger.info(f"批量任务已提交: job_id={job_id}, 任务数={len(request.items)}")
    return JSONResponse(status_code=202, content={"job_id": job_id, "status": "pending"})


# ============ 后台批量任务 ============

async def _run_batch_job(
    job_id: str,
    items: List[BatchItem],
    user: CurrentUser,
):
    """串行执行批量任务项，单项失败不影响其余"""
    update_job(job_id, "ocr")

    for idx, item in enumerate(items):
        update_batch_item(job_id, idx, "processing")
        try:
            if item.type == "single":
                await _process_single_item(job_id, idx, item, user)
            else:
                await _process_merge_item(job_id, idx, item, user)
        except Exception as e:
            logger.error(f"[job={job_id}] 任务项 {idx} 异常: {e}")
            update_batch_item(job_id, idx, "failed", error=str(e))

    # 全部完成
    update_job(job_id, "completed")
    logger.info(f"[job={job_id}] 批量任务全部完成")


async def _process_single_item(
    job_id: str, idx: int, item: BatchItem, user: CurrentUser
):
    """处理单个 single 任务项"""
    doc = await supabase_service.get_document(item.document_id)
    file_path = doc.get("file_path", "")
    if not file_path or not os.path.exists(file_path):
        update_batch_item(job_id, idx, "failed", error="文件不存在")
        return

    template = await template_service.get_template(item.template_id)
    auto_approve = bool(template.get("auto_approve", False)) if template else False

    result = await ocr_workflow.process_with_template(
        document_id=item.document_id,
        file_path=file_path,
        template_id=item.template_id,
        tenant_id=user.tenant_id,
    )

    if result.get("success") and result.get("extraction_data"):
        await handle_processing_success(
            document_id=item.document_id,
            result=result,
            template_id=item.template_id,
            tenant_id=user.tenant_id,
            generate_display_name=True,
            auto_approve=auto_approve,
            source_file_path=file_path,
        )
        update_batch_item(job_id, idx, "completed", document_ids=[item.document_id])
    else:
        error_msg = result.get("error", "处理失败")
        await handle_processing_failure(item.document_id, error_msg)
        update_batch_item(job_id, idx, "failed", error=error_msg)


async def _process_merge_item(
    job_id: str, idx: int, item: BatchItem, user: CurrentUser
):
    """处理单个 merge 任务项"""
    doc_a = await supabase_service.get_document(item.document_id_a)
    doc_b = await supabase_service.get_document(item.document_id_b)
    fp_a = doc_a.get("file_path", "") if doc_a else ""
    fp_b = doc_b.get("file_path", "") if doc_b else ""

    if not fp_a or not os.path.exists(fp_a):
        update_batch_item(job_id, idx, "failed", error=f"文件 A 不存在: {fp_a}")
        return
    if not fp_b or not os.path.exists(fp_b):
        update_batch_item(job_id, idx, "failed", error=f"文件 B 不存在: {fp_b}")
        return

    template = await template_service.get_template_with_details(item.template_id)
    if not template:
        update_batch_item(job_id, idx, "failed", error="模板不存在")
        return

    template_uuid = template.get("id")
    template_name = template.get("name", "综合报告")
    auto_approve = bool(template.get("auto_approve", False))

    files = [
        {"file_path": fp_a, "doc_type": item.doc_type_a},
        {"file_path": fp_b, "doc_type": item.doc_type_b},
    ]

    result = await ocr_workflow.process_merge(
        document_id=str(uuid.uuid4()),
        files=files,
        template_id=template_uuid,
        tenant_id=user.tenant_id,
    )

    if not result.get("success"):
        error_msg = result.get("error", "合并处理失败")
        update_batch_item(job_id, idx, "failed", error=error_msg)
        return

    extraction_results = result.get("extraction_results", [])
    if not extraction_results:
        update_batch_item(job_id, idx, "failed", error="未提取到有效字段")
        return

    created_doc_ids = []
    sample_count = len(extraction_results)
    source_doc_ids = [item.document_id_a, item.document_id_b]

    for sample_result in extraction_results:
        sample_index = sample_result.get("sample_index", 1)
        sample_data = sample_result.get("data", {})
        if not sample_data:
            continue

        doc_id = str(uuid.uuid4())
        created_doc_ids.append(doc_id)

        base_display_name = supabase_service.generate_display_name(
            document_type=template_name, extraction_data=sample_data,
        )
        display_name = (
            f"{base_display_name}_样品{sample_index}" if sample_count > 1 else base_display_name
        )
        doc_status = "completed" if auto_approve else "pending_review"

        doc_data = {
            "id": doc_id,
            "user_id": user.user_id,
            "tenant_id": user.tenant_id,
            "template_id": template_uuid,
            "document_type": template_name,
            "status": doc_status,
            "display_name": display_name,
            "original_file_name": display_name,
            "file_name": f"merged_{doc_id}",
            "file_path": "",
            "source_document_ids": source_doc_ids,
            "ocr_confidence": result.get("ocr_confidence"),
            "processed_at": datetime.now().isoformat(),
        }
        await supabase_service.create_document(doc_data)
        await supabase_service.save_extraction_result(
            document_id=doc_id,
            document_type=template_name,
            extraction_data=sample_data,
        )

        if auto_approve:
            try:
                await push_to_feishu(
                    template=template,
                    extraction_data=sample_data,
                    display_name=display_name,
                    document_id=doc_id,
                    log_prefix=f"[job={job_id}] batch-merge 样品{sample_index} ",
                )
            except Exception as feishu_err:
                logger.warning(f"[job={job_id}] 飞书推送失败: {feishu_err}")

    update_batch_item(job_id, idx, "completed", document_ids=created_doc_ids)
    logger.info(f"[job={job_id}] merge 任务项 {idx} 完成, docs={created_doc_ids}")
