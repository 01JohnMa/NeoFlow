# agents/workflow.py
"""LangGraph OCR处理工作流 - 基于MVP代码 supervise_agentic.py 重构"""

from datetime import datetime
from typing import TypedDict, Annotated, Any, Dict, Optional

import httpx
from langchain_core.messages import HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.settings import settings
from services.ocr_service import ocr_service
from services.template_service import template_service
from .exceptions import WorkflowError, WorkflowErrorType
from .json_cleaner import parse_llm_json
from .result_builder import build_error, build_single_success, build_merge_success


# LLM 可重试的异常类型
LLM_RETRYABLE_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.ConnectError,
)


class WorkflowState(TypedDict):
    """工作流状态定义"""
    messages: Annotated[list, add_messages]
    document_id: str
    file_path: str
    ocr_text: str
    ocr_confidence: float
    document_type: str
    extraction_data: dict
    step: str
    error: Optional[str]
    processing_start: Optional[datetime]
    tenant_id: Optional[str]  # 租户ID，用于查询模板配置


class OCRWorkflow:
    """OCR处理工作流 - 基于MVP代码重构"""

    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL_ID,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=settings.LLM_TEMPERATURE,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
        self.memory = MemorySaver()
        self.workflow = self._build_workflow()
        self._text_workflow = self._build_text_workflow()

    def _build_workflow(self) -> StateGraph:
        workflow = StateGraph(WorkflowState)

        if settings.DOC_PROCESS_MODE == "vlm":
            # VLM 模式：单节点，直接从图片提取
            workflow.add_node("vlm_extract", self._vlm_node)
            workflow.add_edge(START, "vlm_extract")
            workflow.add_edge("vlm_extract", END)
        else:
            # ocr_llm 模式（默认）：OCR → 字段提取（无分类节点）
            workflow.add_node("ocr_extract", self._ocr_node)
            workflow.add_node("extract", self._extract_node)
            workflow.add_edge(START, "ocr_extract")
            workflow.add_edge("ocr_extract", "extract")
            workflow.add_edge("extract", END)

        return workflow.compile(checkpointer=self.memory)

    def _build_text_workflow(self) -> StateGraph:
        """预编译跳过OCR步骤的简化工作流（供 process_with_text 复用）"""
        wf = StateGraph(WorkflowState)
        wf.add_node("extract", self._extract_node)
        wf.add_edge(START, "extract")
        wf.add_edge("extract", END)
        return wf.compile(checkpointer=self.memory)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(LLM_RETRYABLE_EXCEPTIONS),
        reraise=True,
    )
    async def _llm_invoke_with_retry(self, prompt: str) -> str:
        """带重试的 LLM 调用。重试耗尽后抛出最后一次异常。"""
        response = await self.llm.ainvoke(prompt)
        return response.content

    # ============ LangGraph 节点 ============

    async def _ocr_node(self, state: WorkflowState) -> Dict[str, Any]:
        """OCR提取节点"""
        file_path = state.get("file_path", "")
        if not file_path:
            raise WorkflowError(WorkflowErrorType.VALIDATION_ERROR, "文件路径为空")

        try:
            logger.info(f"开始OCR处理: {file_path}")
            result = await ocr_service.process_document(file_path)
            logger.info(f"OCR完成，提取{result['total_lines']}行，置信度{result['confidence']:.2f}")
            return {
                "ocr_text": result["text"],
                "ocr_confidence": result["confidence"],
                "step": "ocr_completed",
                "messages": [AIMessage(content=f"OCR提取完成，共{result['total_lines']}行文本")],
            }
        except WorkflowError:
            raise
        except Exception as e:
            logger.error(f"OCR处理失败: {e}")
            raise WorkflowError(WorkflowErrorType.OCR_FAILED, str(e))

    async def _extract_node(self, state: WorkflowState) -> Dict[str, Any]:
        """字段提取节点 - 从数据库获取模板配置构建 prompt（ocr_llm 模式）"""
        doc_type = state.get("document_type", "")
        ocr_text = state.get("ocr_text", "")
        tenant_id = state.get("tenant_id")

        logger.info(f"开始字段提取，文档类型: {doc_type}, 租户: {tenant_id}")

        if not tenant_id:
            logger.error(f"字段提取失败: 文档 {state.get('document_id')} 缺少租户ID，请确保用户已选择所属部门")
            raise WorkflowError(WorkflowErrorType.VALIDATION_ERROR, "缺少租户ID，用户未选择所属部门")

        if not doc_type:
            raise WorkflowError(WorkflowErrorType.VALIDATION_ERROR, "缺少文档类型，无法获取模板配置")

        try:
            template = await template_service.get_template_by_code(tenant_id, doc_type)
            if not template:
                raise WorkflowError(
                    WorkflowErrorType.TEMPLATE_NOT_FOUND,
                    f"未找到文档类型 [{doc_type}] 的模板配置",
                )

            prompt = template_service.build_extraction_prompt(template, ocr_text)
            logger.info(f"使用数据库模板 [{template.get('name')}] 构建 prompt")

            response_content = await self._llm_invoke_with_retry(prompt)
            extraction_data = parse_llm_json(response_content)

            logger.info(f"字段提取完成: {len(extraction_data)}个字段")
            return {
                "extraction_data": extraction_data,
                "step": "completed",
                "messages": [AIMessage(content=f"字段提取完成: {str(extraction_data)[:200]}...")],
            }
        except WorkflowError:
            raise
        except Exception as e:
            logger.error(f"提取失败: {e}")
            raise WorkflowError(WorkflowErrorType.EXTRACT_FAILED, str(e))

    async def _vlm_node(self, state: WorkflowState) -> Dict[str, Any]:
        """VLM 多模态提取节点（vlm 模式）

        直接从图片提取字段，不经过 OCR 转文字。
        文档类型由用户上传时手动选择（通过 template_id 关联），
        从 state.document_type 取得（由调用方传入）。
        """
        from services.vlm_service import vlm_service

        file_path = state.get("file_path", "")
        doc_type = state.get("document_type", "")
        tenant_id = state.get("tenant_id")

        if not file_path:
            raise WorkflowError(WorkflowErrorType.VALIDATION_ERROR, "文件路径为空")
        if not tenant_id:
            raise WorkflowError(WorkflowErrorType.VALIDATION_ERROR, "缺少租户ID，用户未选择所属部门")
        if not doc_type:
            raise WorkflowError(WorkflowErrorType.VALIDATION_ERROR, "缺少文档类型，请上传时选择文档类型")

        try:
            template = await template_service.get_template_by_code(tenant_id, doc_type)
            if not template:
                raise WorkflowError(
                    WorkflowErrorType.TEMPLATE_NOT_FOUND,
                    f"未找到文档类型 [{doc_type}] 的模板配置",
                )

            logger.info(f"VLM 模式提取: {file_path}，模板: {template.get('name')}")
            extraction_data = await vlm_service.extract_from_image(file_path, template)

            logger.info(f"VLM 提取完成: {len(extraction_data)} 个字段")
            return {
                "extraction_data": extraction_data,
                "ocr_text": "",       # VLM 模式无 OCR 文本
                "ocr_confidence": 0.0,
                "step": "completed",
                "messages": [AIMessage(content=f"VLM提取完成: {str(extraction_data)[:200]}...")],
            }
        except WorkflowError:
            raise
        except Exception as e:
            logger.error(f"VLM 提取失败: {e}")
            raise WorkflowError(WorkflowErrorType.EXTRACT_FAILED, str(e))

    # ============ 辅助方法 ============

    def _elapsed(self, start: datetime) -> float:
        return (datetime.now() - start).total_seconds()

    # ============ 公共处理入口 ============

    async def process(
        self,
        document_id: str,
        file_path: str,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """执行工作流 - 主入口（自动分类模式）

        Args:
            document_id: 文档ID
            file_path: 文件路径
            tenant_id: 租户ID（可选，用于从数据库获取模板配置）
        """
        processing_start = datetime.now()

        initial_state: WorkflowState = {
            "messages": [],
            "document_id": document_id,
            "file_path": file_path,
            "ocr_text": "",
            "ocr_confidence": 0.0,
            "document_type": "",
            "extraction_data": {},
            "step": "start",
            "error": None,
            "processing_start": processing_start,
            "tenant_id": tenant_id,
        }

        config = {"configurable": {"thread_id": document_id}}

        try:
            final_state = await self.workflow.ainvoke(initial_state, config=config)
            return build_single_success(
                document_id=document_id,
                document_type=final_state.get("document_type", ""),
                extraction_data=final_state.get("extraction_data", {}),
                ocr_text=final_state.get("ocr_text", ""),
                ocr_confidence=final_state.get("ocr_confidence", 0.0),
                processing_time=self._elapsed(processing_start),
            )
        except Exception as e:
            logger.error(f"工作流执行失败: {e}")
            err_msg = WorkflowError.extract_message(e)
            return build_error(document_id, err_msg, self._elapsed(processing_start))

    async def process_with_text(
        self,
        document_id: str,
        ocr_text: str,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """使用已有OCR文本执行工作流（跳过OCR步骤，无分类节点）

        用于已经完成OCR的场景，直接进行字段提取。
        需要在 state 中预设 document_type（由调用方传入）。

        Args:
            document_id: 文档ID
            ocr_text: OCR提取的文本
            tenant_id: 租户ID（可选，用于从数据库获取模板配置）
        """
        processing_start = datetime.now()

        initial_state: WorkflowState = {
            "messages": [HumanMessage(content=ocr_text)],
            "document_id": document_id,
            "file_path": "",
            "ocr_text": ocr_text,
            "ocr_confidence": 1.0,
            "document_type": "",
            "extraction_data": {},
            "step": "ocr_completed",
            "error": None,
            "processing_start": processing_start,
            "tenant_id": tenant_id,
        }

        # 简化工作流（跳过OCR节点，无分类节点）
        config = {"configurable": {"thread_id": f"{document_id}-text"}}

        try:
            final_state = await self._text_workflow.ainvoke(initial_state, config=config)
            return build_single_success(
                document_id=document_id,
                document_type=final_state.get("document_type", ""),
                extraction_data=final_state.get("extraction_data", {}),
                ocr_text=ocr_text,
                ocr_confidence=1.0,
                processing_time=self._elapsed(processing_start),
            )
        except Exception as e:
            logger.error(f"工作流执行失败: {e}")
            err_msg = WorkflowError.extract_message(e)
            return build_error(document_id, err_msg, self._elapsed(processing_start))

    # ============ 模板化提取方法 ============

    async def process_with_template(
        self,
        document_id: str,
        file_path: str,
        template_id: str,
        tenant_id: str,
    ) -> Dict[str, Any]:
        """使用模板配置执行工作流（单文档）

        根据 DOC_PROCESS_MODE 自动选择 OCR+LLM 或 VLM 路径。

        Args:
            document_id: 文档ID
            file_path: 文件路径
            template_id: 模板ID
            tenant_id: 租户ID
        """
        processing_start = datetime.now()

        try:
            template = await template_service.get_template_with_details(template_id)
            if not template:
                raise WorkflowError(
                    WorkflowErrorType.TEMPLATE_NOT_FOUND,
                    f"模板不存在: {template_id}",
                )

            logger.info(
                f"使用模板 [{template['name']}] 处理文档，模式: {template.get('extraction_mode', settings.DOC_PROCESS_MODE)}"
            )

            mode = template.get("extraction_mode", settings.DOC_PROCESS_MODE)
            if mode == "vlm":
                # ── VLM 路径：直接从图片提取 ──────────────────────────────
                from services.vlm_service import vlm_service

                extraction_data = await vlm_service.extract_from_image(file_path, template)
                ocr_text = ""
                ocr_confidence = 0.0
            else:
                # ── OCR+LLM 路径（默认）──────────────────────────────────
                logger.info(f"开始OCR处理: {file_path}")
                ocr_result = await ocr_service.process_document(file_path)
                ocr_text = ocr_result["text"]
                ocr_confidence = ocr_result["confidence"]
                logger.info(
                    f"OCR完成，提取{ocr_result['total_lines']}行，置信度{ocr_confidence:.2f}"
                )

                prompt = template_service.build_extraction_prompt(template, ocr_text)
                response_content = await self._llm_invoke_with_retry(prompt)
                extraction_data = parse_llm_json(response_content)

            processing_time = self._elapsed(processing_start)
            logger.info(f"模板化提取完成: {len(extraction_data)}个字段，耗时{processing_time:.2f}s")

            return build_single_success(
                document_id=document_id,
                document_type=template.get("code", ""),
                extraction_data=extraction_data,
                ocr_text=ocr_text,
                ocr_confidence=ocr_confidence,
                processing_time=processing_time,
                template_id=template_id,
                template_name=template.get("name"),
            )

        except Exception as e:
            logger.error(f"模板化处理失败: {e}")
            err_msg = WorkflowError.extract_message(e)
            return build_error(document_id, err_msg, self._elapsed(processing_start))

    async def process_merge(
        self,
        document_id: str,
        files: list,  # [{file_path, doc_type}, ...]
        template_id: str,
        tenant_id: str,
    ) -> Dict[str, Any]:
        """Merge 模式处理：多份文档分别提取后合并

        用于照明事业部等场景：上传积分球+光分布两份文档，
        分别用各自的子模板提取，然后合并结果。

        支持多样品场景：积分球 PDF 可能有多页（每页一个样品），
        每个样品的积分球数据会与同一份光分布数据合并，生成多条结果。

        Args:
            document_id: 文档ID
            files: 文件列表，每项包含 file_path 和 doc_type
            template_id: 合并模板ID（process_mode='merge'）
            tenant_id: 租户ID
        """
        processing_start = datetime.now()

        try:
            template = await template_service.get_merge_template_info(template_id)
            if not template:
                raise WorkflowError(
                    WorkflowErrorType.TEMPLATE_NOT_FOUND,
                    f"模板不存在: {template_id}",
                )

            if template.get("process_mode") != "merge":
                raise WorkflowError(
                    WorkflowErrorType.VALIDATION_ERROR,
                    f"模板 {template['name']} 不是合并模式",
                )

            logger.info(f"使用合并模板 [{template['name']}] 处理 {len(files)} 份文档")

            merge_rule = await template_service.get_merge_rule(template_id)
            if not merge_rule:
                raise WorkflowError(
                    WorkflowErrorType.VALIDATION_ERROR,
                    "合并规则配置缺失",
                )

            sub_template_a = template.get("sub_template_a")
            sub_template_b = template.get("sub_template_b")

            # doc_type_a（如积分球）支持多样品（逐页提取）
            # doc_type_b（如光分布）保持单一结果
            results_a = []
            result_b = None

            for file_info in files:
                file_path = file_info.get("file_path")
                doc_type = file_info.get("doc_type", "")

                if not file_path:
                    continue

                if doc_type == merge_rule.get("doc_type_a") and sub_template_a:
                    # doc_type_a（积分球）：逐页处理，支持多样品
                    # 当 sub_template_a 与主模板自引用时（积分球升格为主模板场景），
                    # 仅保留 source_doc_type == doc_type_a 的字段构建提取 prompt，
                    # 避免将光分布字段混入积分球提取指令
                    doc_type_a_label = merge_rule.get("doc_type_a", "")
                    if sub_template_a.get("id") == template.get("id") and doc_type_a_label:
                        extraction_template_a = {
                            **sub_template_a,
                            "template_fields": [
                                f for f in sub_template_a.get("template_fields", [])
                                if f.get("source_doc_type") == doc_type_a_label
                            ],
                        }
                        logger.info(
                            f"sub_template_a 自引用，按 source_doc_type='{doc_type_a_label}' "
                            f"过滤后字段数: {len(extraction_template_a['template_fields'])}"
                        )
                    else:
                        extraction_template_a = sub_template_a

                    logger.info(f"逐页OCR处理文档A: {file_path} (类型: {doc_type})")
                    page_results = await ocr_service.process_document_per_page(file_path)

                    for page in page_results:
                        extracted = parse_llm_json(
                            await self._llm_invoke_with_retry(
                                template_service.build_extraction_prompt(extraction_template_a, page["text"])
                            )
                        )
                        results_a.append(extracted)
                        logger.info(f"文档A 第{page['page']}页提取完成: {len(extracted)}个字段")

                    logger.info(f"文档A ({doc_type}) 共提取 {len(results_a)} 个样品")

                elif doc_type == merge_rule.get("doc_type_b") and sub_template_b:
                    # doc_type_b（光分布）：整体处理
                    logger.info(f"OCR处理文档B: {file_path} (类型: {doc_type})")
                    ocr_result = await ocr_service.process_document(file_path)
                    result_b = parse_llm_json(
                        await self._llm_invoke_with_retry(
                            template_service.build_extraction_prompt(sub_template_b, ocr_result["text"])
                        )
                    )
                    logger.info(f"文档B ({doc_type}) 提取完成: {len(result_b)}个字段")

            # 合并结果：每个 doc_type_a 样品 + 同一份 doc_type_b 数据
            if results_a:
                extraction_results = [
                    {
                        "sample_index": i + 1,
                        "data": template_service.merge_extraction_results(result_a, result_b),
                    }
                    for i, result_a in enumerate(results_a)
                ]
            else:
                # 无 doc_type_a 时，仅返回 doc_type_b
                extraction_results = [{"sample_index": 1, "data": result_b or {}}]

            processing_time = self._elapsed(processing_start)
            logger.info(f"合并提取完成: {len(extraction_results)}个样品，耗时{processing_time:.2f}s")

            return build_merge_success(
                document_id=document_id,
                template_id=template_id,
                template_name=template.get("name", ""),
                document_type=template.get("code", ""),
                extraction_results=extraction_results,
                results_a=results_a,
                result_b=result_b,
                processing_time=processing_time,
            )

        except Exception as e:
            logger.error(f"合并处理失败: {e}")
            err_msg = WorkflowError.extract_message(e)
            return build_error(document_id, err_msg, self._elapsed(processing_start))

    async def process_auto(
        self,
        document_id: str,
        files: list,  # [{file_path, doc_type?}, ...]
        template_id: str,
        tenant_id: str,
    ) -> Dict[str, Any]:
        """统一处理入口，自动根据模板的 process_mode 选择处理方式

        这是推荐的处理入口，会根据模板配置自动选择：
        - single 模式：调用 process_with_template()
        - merge 模式：调用 process_merge()

        Args:
            document_id: 文档ID
            files: 文件列表，每项包含 file_path 和可选的 doc_type
                   单文档模式: [{"file_path": "xxx"}]
                   合并模式: [{"file_path": "xxx", "doc_type": "积分球"}, ...]
            template_id: 模板ID
            tenant_id: 租户ID
        """
        try:
            template = await template_service.get_template(template_id)
            if not template:
                return build_error(document_id, f"模板不存在: {template_id}")

            process_mode = template.get("process_mode", "single")
            logger.info(f"统一处理入口: 模板={template.get('name')}, 模式={process_mode}, 文件数={len(files)}")

            if process_mode == "merge":
                return await self.process_merge(
                    document_id=document_id,
                    files=files,
                    template_id=template_id,
                    tenant_id=tenant_id,
                )

            # 单文档模式
            if not files:
                return build_error(document_id, "文件列表为空")

            file_path = files[0].get("file_path")
            if not file_path:
                return build_error(document_id, "文件路径为空")

            return await self.process_with_template(
                document_id=document_id,
                file_path=file_path,
                template_id=template_id,
                tenant_id=tenant_id,
            )

        except Exception as e:
            logger.error(f"统一处理入口失败: {e}")
            err_msg = WorkflowError.extract_message(e)
            return build_error(document_id, err_msg)

    async def extract_with_prompt(
        self,
        prompt_template: str,
    ) -> Dict[str, Any]:
        """使用指定 Prompt 模板提取字段（底层方法）

        Args:
            prompt_template: Prompt 模板（已包含字段定义和示例）

        Returns:
            提取的字段字典
        """
        try:
            response_content = await self._llm_invoke_with_retry(prompt_template)
            return parse_llm_json(response_content)
        except Exception as e:
            logger.error(f"字段提取失败: {e}")
            return {"error": str(e)}


# 单例工作流
ocr_workflow = OCRWorkflow()
