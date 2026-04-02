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
from api.jobs import (
    build_batch_dedupe_key,
    build_feishu_push_dedupe_key,
    create_job,
    find_job_by_dedupe_key,
    update_job,
    update_batch_item,
    get_job,
)
from .helpers import (
    handle_processing_success,
    handle_processing_failure,
    push_to_feishu,
)

router = APIRouter()


# ============ 请求模型 ============

class BatchItem(BaseModel):
    document_id: str
    template_id: str
    paired_template_id: Optional[str] = None
    paired_document_id: Optional[str] = None
    custom_push_name: Optional[str] = None

    @validator("paired_document_id")
    def validate_pair(cls, v, values):
        if v and not values.get("paired_template_id"):
            raise ValueError("配对模式需要同时提供 paired_template_id")
        return v


class BatchProcessRequest(BaseModel):
    items: List[BatchItem]

    @validator("items")
    def validate_items_count(cls, v):
        if len(v) == 0:
            raise ValueError("至少需要一个任务项")
        if len(v) > 10:
            raise ValueError("单次批量最多 10 个任务项")
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

        doc = await supabase_service.get_document(item.document_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"任务项 {idx+1}: 文档不存在")

        if item.paired_document_id:
            paired_doc = await supabase_service.get_document(item.paired_document_id)
            if not paired_doc:
                raise HTTPException(status_code=404, detail=f"任务项 {idx+1}: 配对文档不存在")

    # 构建 batch items 结构
    batch_items = []
    dedupe_items = []
    related_document_ids: list[str] = []
    for idx, item in enumerate(request.items):
        is_merge = bool(item.paired_document_id)
        doc_ids = [doc_id for doc_id in [item.document_id, item.paired_document_id] if doc_id]
        batch_items.append({
            "index": idx,
            "type": "merge" if is_merge else "single",
            "document_ids": doc_ids,
            "status": "queued",
        })
        dedupe_items.append(item.model_dump())
        related_document_ids.extend(doc_ids)

    dedupe_key = build_batch_dedupe_key(dedupe_items)
    existing_job = await find_job_by_dedupe_key(dedupe_key)
    if existing_job:
        return JSONResponse(status_code=202, content={"job_id": existing_job["job_id"], "status": existing_job["status"]})

    unique_document_ids = list(dict.fromkeys(related_document_ids))
    for document_id in unique_document_ids:
        await _set_document_status_safe(document_id, "queued")

    job_id = await create_job(
        batch_items=batch_items,
        job_type="batch",
        created_by=user.user_id,
        dedupe_key=dedupe_key,
        related_document_ids=unique_document_ids,
    )
    asyncio.create_task(_run_batch_job(job_id, request.items, user))
    logger.info(f"批量任务已提交: job_id={job_id}, 任务数={len(request.items)}")
    return JSONResponse(status_code=202, content={"job_id": job_id, "status": "queued"})


# ============ 后台批量任务 ============

async def _set_document_status_safe(document_id: Optional[str], status: str, error_message: Optional[str] = None):
    if not document_id:
        return
    try:
        await supabase_service.update_document_status(document_id, status, error_message=error_message)
    except Exception as exc:
        logger.warning(f"更新文档状态失败: doc={document_id}, status={status}, err={exc}")


async def _set_item_documents_status(item: BatchItem, status: str, error_message: Optional[str] = None):
    await _set_document_status_safe(item.document_id, status, error_message=error_message)
    if item.paired_document_id:
        await _set_document_status_safe(item.paired_document_id, status, error_message=error_message)


async def _run_batch_job(
    job_id: str,
    items: List[BatchItem],
    user: CurrentUser,
):
    """串行执行批量任务项，单项失败不影响其余"""
    await update_job(job_id, "ocr")

    for idx, item in enumerate(items):
        await update_batch_item(job_id, idx, "processing")
        await _set_item_documents_status(item, "processing")
        try:
            if item.paired_document_id:
                await _process_merge_item(job_id, idx, item, user)
            else:
                await _process_single_item(job_id, idx, item, user)
        except Exception as e:
            logger.error(f"[job={job_id}] 任务项 {idx} 异常: {e}")
            await _set_item_documents_status(item, "failed", error_message=str(e))
            await update_batch_item(job_id, idx, "failed", error=str(e))

    final_job = await get_job(job_id)
    if final_job and final_job.get("status") == "failed":
        await update_job(job_id, "failed", error=final_job.get("error"))
    else:
        await update_job(job_id, "completed", document_ids=(final_job or {}).get("document_ids", []), error=None)
    logger.info(f"[job={job_id}] 批量任务全部完成")


async def _process_single_item(
    job_id: str, idx: int, item: BatchItem, user: CurrentUser
):
    """处理单个 single 任务项"""
    doc = await supabase_service.get_document(item.document_id)
    file_path = doc.get("file_path", "")
    if not file_path or not os.path.exists(file_path):
        await _set_item_documents_status(item, "failed", error_message="文件不存在")
        await update_batch_item(job_id, idx, "failed", error="文件不存在")
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
        extraction_results = result.get("extraction_results")  # 逐页多样品时存在
        base_push_name = item.custom_push_name or (doc.get("custom_push_name") if doc else None)

        if extraction_results and len(extraction_results) > 1 and auto_approve:
            # 逐页多样品 + auto_approve：每个样品单独推送
            template_detail = await template_service.get_template_with_details(item.template_id)
            sample_count = len(extraction_results)
            for sample_result in extraction_results:
                sample_index = sample_result.get("sample_index", 1)
                sample_data = sample_result.get("data", {})
                if not sample_data:
                    continue
                if sample_count > 1 and base_push_name:
                    custom_push_name = f"{base_push_name}_{sample_index}"
                else:
                    custom_push_name = base_push_name
                try:
                    await push_to_feishu(
                        template=template_detail,
                        extraction_data=sample_data,
                        display_name=supabase_service.generate_display_name(
                            document_type=template_detail.get("name", ""),
                            extraction_data=sample_data,
                        ),
                        document_id=f"{item.document_id}-sample-{sample_index}",
                        source_file_path=file_path if template_detail.get("push_attachment", True) else None,
                        log_prefix=f"[job={job_id}] single 样品{sample_index} ",
                        custom_push_name=custom_push_name,
                        dedupe_key=build_feishu_push_dedupe_key(
                            f"single:{item.document_id}:sample:{sample_index}",
                            item.template_id,
                            sample_data,
                        ),
                    )
                except Exception as feishu_err:
                    logger.warning(f"[job={job_id}] 飞书推送失败(样品{sample_index}): {feishu_err}")
            # 保存第一个样品的提取结果到原文档
            await handle_processing_success(
                document_id=item.document_id,
                result=result,
                template_id=item.template_id,
                tenant_id=user.tenant_id,
                generate_display_name=True,
                auto_approve=auto_approve,
                source_file_path=file_path,
                custom_push_name=None,  # 已在上面逐样品推送，这里不再重复
            )
        else:
            await handle_processing_success(
                document_id=item.document_id,
                result=result,
                template_id=item.template_id,
                tenant_id=user.tenant_id,
                generate_display_name=True,
                auto_approve=auto_approve,
                source_file_path=file_path,
                custom_push_name=base_push_name,
            )
        await update_batch_item(job_id, idx, "completed", document_ids=[item.document_id])
    else:
        error_msg = result.get("error", "处理失败")
        await handle_processing_failure(item.document_id, error_msg)
        await update_batch_item(job_id, idx, "failed", error=error_msg)


async def _process_merge_item(
    job_id: str, idx: int, item: BatchItem, user: CurrentUser
):
    """处理单个 merge 任务项（按文件顺序分配子模板）"""
    doc_a = await supabase_service.get_document(item.document_id)
    doc_b = await supabase_service.get_document(item.paired_document_id)
    fp_a = doc_a.get("file_path", "") if doc_a else ""
    fp_b = doc_b.get("file_path", "") if doc_b else ""

    if not fp_a or not os.path.exists(fp_a):
        await _set_item_documents_status(item, "failed", error_message=f"文件 A 不存在: {fp_a}")
        await update_batch_item(job_id, idx, "failed", error=f"文件 A 不存在: {fp_a}")
        return
    if not fp_b or not os.path.exists(fp_b):
        await _set_item_documents_status(item, "failed", error_message=f"文件 B 不存在: {fp_b}")
        await update_batch_item(job_id, idx, "failed", error=f"文件 B 不存在: {fp_b}")
        return

    sub_template_a = await template_service.get_template_with_details(item.template_id)
    if not sub_template_a:
        await _set_item_documents_status(item, "failed", error_message="模板 A 不存在")
        await update_batch_item(job_id, idx, "failed", error="模板 A 不存在")
        return
    sub_template_b = await template_service.get_template_with_details(item.paired_template_id)
    if not sub_template_b:
        await _set_item_documents_status(item, "failed", error_message="模板 B 不存在")
        await update_batch_item(job_id, idx, "failed", error="模板 B 不存在")
        return

    template_name = sub_template_a.get("name", "综合报告")
    auto_approve = bool(sub_template_a.get("auto_approve", False))

    files = [
        {"file_path": fp_a},
        {"file_path": fp_b},
    ]

    result = await ocr_workflow.process_merge(
        document_id=str(uuid.uuid4()),
        files=files,
        sub_template_a_id=item.template_id,
        sub_template_b_id=item.paired_template_id,
        tenant_id=user.tenant_id,
    )

    if not result.get("success"):
        error_msg = result.get("error", "合并处理失败")
        await _set_item_documents_status(item, "failed", error_message=error_msg)
        await update_batch_item(job_id, idx, "failed", error=error_msg)
        return

    extraction_results = result.get("extraction_results", [])
    if not extraction_results:
        await _set_item_documents_status(item, "failed", error_message="未提取到有效字段")
        await update_batch_item(job_id, idx, "failed", error="未提取到有效字段")
        return

    sub_results = result.get("sub_results", {})
    results_a = sub_results.get("results_a", [])
    results_b = sub_results.get("results_b", [])

    doc_a_id = item.document_id
    doc_b_id = item.paired_document_id
    created_doc_ids = []

    if auto_approve:
        base_push_name = item.custom_push_name or (doc_a.get("custom_push_name") if doc_a else None)
        sample_count = len(extraction_results)
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
            # 多样品时推送名拼接序号，单样品保持原样
            if sample_count > 1 and base_push_name:
                custom_push_name = f"{base_push_name}_{sample_index}"
            else:
                custom_push_name = base_push_name
            try:
                # 根据各自模板的 push_attachment 决定推哪些文件
                merge_file_paths = []
                if sub_template_a.get("push_attachment", True) and fp_a:
                    merge_file_paths.append(fp_a)
                if sub_template_b.get("push_attachment", True) and fp_b:
                    merge_file_paths.append(fp_b)
                await push_to_feishu(
                    template=sub_template_a,
                    extraction_data=sample_data,
                    display_name=display_name,
                    document_id=f"batch-merge-{job_id}-{idx}-{sample_index}",
                    source_file_path=merge_file_paths or None,
                    log_prefix=f"[job={job_id}] batch-merge 样品{sample_index} ",
                    extra_template=sub_template_b,
                    custom_push_name=custom_push_name,
                    dedupe_key=build_feishu_push_dedupe_key(
                        f"merge:{doc_a_id}:{doc_b_id}:sample:{sample_index}",
                        item.template_id,
                        sample_data,
                    ),
                )
            except Exception as feishu_err:
                logger.warning(f"[job={job_id}] 飞书推送失败: {feishu_err}")

        await _set_item_documents_status(item, "completed")
        await update_batch_item(job_id, idx, "completed", document_ids=[doc_a_id, doc_b_id])
        logger.info(f"[job={job_id}] merge 任务项 {idx} auto_approve 推送完成")
        return

    # 非 auto_approve：各文档只存自己的原始字段，记录配对关系
    first_doc_a_id = None
    sub_a_code = sub_template_a.get("code", "")
    for i, result_a_data in enumerate(results_a):
        sample_index = i + 1
        if not result_a_data:
            continue

        if len(results_a) <= 1:
            current_doc_a_id = doc_a_id
        else:
            current_doc_a_id = str(uuid.uuid4())
            created_doc_ids.append(current_doc_a_id)
            display_name = supabase_service.generate_display_name(
                document_type=template_name, extraction_data=result_a_data,
            )
            await supabase_service.create_document({
                "id": current_doc_a_id,
                "user_id": user.user_id,
                "tenant_id": user.tenant_id,
                "template_id": item.template_id,
                "document_type": sub_a_code,
                "status": "pending_review",
                "display_name": f"{display_name}_样品{sample_index}",
                "original_file_name": f"{display_name}_样品{sample_index}",
                "file_name": f"sample_{current_doc_a_id}",
                "file_path": "",
                "source_document_ids": [doc_a_id],
                "processed_at": datetime.now().isoformat(),
            })

        if first_doc_a_id is None:
            first_doc_a_id = current_doc_a_id

        await supabase_service.save_extraction_result(
            document_id=current_doc_a_id,
            document_type=sub_a_code,
            extraction_data=result_a_data,
            template_id=item.template_id,
        )
        await supabase_service.update_document(current_doc_a_id, {
            "status": "pending_review",
            "paired_document_id": doc_b_id,
            "merge_template_id": item.template_id,
        })

    if results_b and doc_b_id:
        sub_b_code = sub_template_b.get("code", "")
        # 合并所有 B 页结果后存（保持一条 extraction_result 记录）
        merged_b = {}
        for rb in results_b:
            merged_b.update(rb)
        await supabase_service.save_extraction_result(
            document_id=doc_b_id,
            document_type=sub_b_code,
            extraction_data=merged_b,
            template_id=item.paired_template_id,
        )
        await supabase_service.update_document(doc_b_id, {
            "status": "pending_review",
            "paired_document_id": first_doc_a_id,
            "merge_template_id": item.template_id,
        })

    all_doc_ids = [doc_a_id] + created_doc_ids + ([doc_b_id] if doc_b_id else [])
    await update_batch_item(job_id, idx, "completed", document_ids=all_doc_ids)
    logger.info(f"[job={job_id}] merge 任务项 {idx} 完成, docs={all_doc_ids}")
