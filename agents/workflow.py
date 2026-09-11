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
from services.base import build_extraction_prompt
from services.configuration_service import configuration_service
from services.ocr_service import ocr_service
from .exceptions import WorkflowError, WorkflowErrorType
from .json_cleaner import parse_llm_json
from .result_builder import build_error, build_single_success


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
        """字段提取节点 - 从 Configuration 获取字段构建 prompt（ocr_llm 模式）"""
        doc_type = state.get("document_type", "")
        ocr_text = state.get("ocr_text", "")
        tenant_id = state.get("tenant_id")

        logger.info(f"开始字段提取，文档类型: {doc_type}, 租户: {tenant_id}")

        if not tenant_id:
            logger.error(f"字段提取失败: 文档 {state.get('document_id')} 缺少租户ID，请确保用户已选择所属部门")
            raise WorkflowError(WorkflowErrorType.VALIDATION_ERROR, "缺少租户ID，用户未选择所属部门")

        if not doc_type:
            raise WorkflowError(WorkflowErrorType.VALIDATION_ERROR, "缺少文档类型，无法获取配置")

        try:
            configuration = await configuration_service.resolve_extraction_configuration(
                tenant_id, doc_type
            )
            if not configuration:
                raise WorkflowError(
                    WorkflowErrorType.TEMPLATE_NOT_FOUND,
                    f"未找到文档类型 [{doc_type}] 的配置",
                )

            prompt = build_extraction_prompt(configuration, ocr_text)
            logger.info(f"使用配置 [{configuration.get('name')}] 构建 prompt")

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
            configuration = await configuration_service.resolve_extraction_configuration(
                tenant_id, doc_type
            )
            if not configuration:
                raise WorkflowError(
                    WorkflowErrorType.TEMPLATE_NOT_FOUND,
                    f"未找到文档类型 [{doc_type}] 的配置",
                )

            logger.info(f"VLM 模式提取: {file_path}，配置: {configuration.get('name')}")
            extraction_data = await vlm_service.extract_from_image(file_path, configuration)

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

    # ============ 配置化提取方法 ============

    async def process_with_configuration(
        self,
        document_id: str,
        file_path: str,
        configuration: Dict[str, Any],
        tenant_id: str,
    ) -> Dict[str, Any]:
        """使用 Configuration 执行工作流（单文档）

        根据 DOC_PROCESS_MODE 自动选择 OCR+LLM 或 VLM 路径。

        Args:
            document_id: 文档ID
            file_path: 文件路径
            configuration: Configuration 抽取执行视图
            tenant_id: 租户ID
        """
        processing_start = datetime.now()
        configuration_id = configuration.get("id")

        try:
            logger.info(
                f"使用配置 [{configuration.get('name')}] 处理文档，"
                f"模式: {configuration.get('extraction_mode', settings.DOC_PROCESS_MODE)}"
            )

            mode = configuration.get("extraction_mode", settings.DOC_PROCESS_MODE)
            per_page = configuration.get("per_page_extraction", False)

            input_mode = configuration.get("extract_input") or "parse"
            if input_mode == "parse":
                from services.parse_service import ensure_parse_result

                parse_data = await ensure_parse_result(
                    document_id=document_id,
                    file_path=file_path,
                    tenant_id=tenant_id,
                )
                if parse_data and parse_data.get("markdown"):
                    logger.info(
                        f"使用 ParseResult 作为抽取输入: {document_id}"
                    )
                    return await self._extract_from_parse(
                        document_id=document_id,
                        configuration=configuration,
                        parse_data=parse_data,
                    )
                logger.info(f"无可用 ParseResult，回退 raw 抽取路径: {document_id}")

            if per_page:
                # ── 逐页提取路径：每页独立提取，每页产生一个样品 ──────────
                if mode == "vlm":
                    from services.vlm_service import vlm_service
                    logger.info(f"VLM逐页处理: {file_path}")
                    vlm_pages = await vlm_service.extract_per_page(file_path, configuration)
                    page_results = [vp["data"] for vp in vlm_pages]
                    ocr_text = ""
                    ocr_confidence = 0.0
                else:
                    logger.info(f"逐页OCR处理: {file_path}")
                    raw_pages = await ocr_service.process_document_per_page(file_path)
                    ocr_text = "\n".join(p["text"] for p in raw_pages)
                    ocr_confidence = raw_pages[0]["confidence"] if raw_pages else 0.0
                    page_results = []
                    for page in raw_pages:
                        extracted = parse_llm_json(
                            await self._llm_invoke_with_retry(
                                build_extraction_prompt(configuration, page["text"])
                            )
                        )
                        page_results.append(extracted)
                        logger.info(f"第{page['page']}页提取完成: {len(extracted)}个字段")

                processing_time = self._elapsed(processing_start)
                logger.info(f"逐页提取完成: {len(page_results)}个样品，耗时{processing_time:.2f}s")

                extraction_results = [
                    {"sample_index": i + 1, "data": data}
                    for i, data in enumerate(page_results)
                ]
                # 用第一页数据作为主 extraction_data（向后兼容）
                extraction_data = page_results[0] if page_results else {}
                result = build_single_success(
                    document_id=document_id,
                    document_type=configuration.get("code", ""),
                    extraction_data=extraction_data,
                    ocr_text=ocr_text,
                    ocr_confidence=ocr_confidence,
                    processing_time=processing_time,
                    template_id=configuration_id,
                    template_name=configuration.get("name"),
                )
                # 多样品时附带完整列表供调用方使用
                if len(extraction_results) > 1:
                    result["extraction_results"] = extraction_results
                return result
            elif mode == "vlm":
                # ── VLM 整体路径：直接从图片提取 ──────────────────────────
                from services.vlm_service import vlm_service

                extraction_data = await vlm_service.extract_from_image(file_path, configuration)
                ocr_text = ""
                ocr_confidence = 0.0
            else:
                # ── OCR+LLM 整体路径（默认）──────────────────────────────
                logger.info(f"开始OCR处理: {file_path}")
                ocr_result = await ocr_service.process_document(file_path)
                ocr_text = ocr_result["text"]
                ocr_confidence = ocr_result["confidence"]
                logger.info(
                    f"OCR完成，提取{ocr_result['total_lines']}行，置信度{ocr_confidence:.2f}"
                )

                prompt = build_extraction_prompt(configuration, ocr_text)
                response_content = await self._llm_invoke_with_retry(prompt)
                extraction_data = parse_llm_json(response_content)

            processing_time = self._elapsed(processing_start)
            logger.info(f"配置化提取完成: {len(extraction_data)}个字段，耗时{processing_time:.2f}s")

            return build_single_success(
                document_id=document_id,
                document_type=configuration.get("code", ""),
                extraction_data=extraction_data,
                ocr_text=ocr_text,
                ocr_confidence=ocr_confidence,
                processing_time=processing_time,
                template_id=configuration_id,
                template_name=configuration.get("name"),
            )

        except Exception as e:
            logger.error(f"配置化处理失败: {e}")
            err_msg = WorkflowError.extract_message(e)
            return build_error(document_id, err_msg, self._elapsed(processing_start))

    async def _extract_from_parse(
        self,
        document_id: str,
        configuration: Dict[str, Any],
        parse_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """以 ParseResult 的 markdown 作为 LLM 输入执行抽取（含逐页模式）。"""
        from services.parse_extraction import run_parse_extraction

        processing_start = datetime.now()
        payload = await run_parse_extraction(
            configuration=configuration,
            parse_data=parse_data,
            llm_invoke=self._llm_invoke_with_retry,
        )
        processing_time = self._elapsed(processing_start)
        logger.info(
            f"ParseResult 抽取完成: {len(payload['extraction_data'])}个字段，"
            f"耗时{processing_time:.2f}s"
        )

        result = build_single_success(
            document_id=document_id,
            document_type=configuration.get("code", ""),
            extraction_data=payload["extraction_data"],
            ocr_text=payload["markdown"],
            ocr_confidence=1.0,
            processing_time=processing_time,
            template_id=configuration.get("id"),
            template_name=configuration.get("name"),
        )
        if payload.get("extraction_results"):
            result["extraction_results"] = payload["extraction_results"]
        return result

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
