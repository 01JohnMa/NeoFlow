# agents/workflow.py
"""配置化抽取工作流：基于 ParseResult 的 markdown 执行 LLM 抽取。

解析（MinerU）由 services.parse_service 负责；本模块只消费解析结果，
不再包含 OCR/VLM 提取模式。
"""

from datetime import datetime
from typing import Any, Dict

import httpx
from langchain_openai import ChatOpenAI
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.settings import settings
from .exceptions import WorkflowError, WorkflowErrorType
from .json_cleaner import parse_llm_json
from .result_builder import build_error, build_single_success


# LLM 可重试的异常类型
LLM_RETRYABLE_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.ConnectError,
)


class DocumentWorkflow:
    """配置化文档抽取工作流。"""

    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL_ID,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=settings.LLM_TEMPERATURE,
            model_kwargs={"response_format": {"type": "json_object"}},
        )

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

    def _elapsed(self, start: datetime) -> float:
        return (datetime.now() - start).total_seconds()

    # ============ 配置化提取方法 ============

    async def process_with_configuration(
        self,
        document_id: str,
        file_path: str,
        configuration: Dict[str, Any],
        tenant_id: str,
    ) -> Dict[str, Any]:
        """使用 Configuration 执行抽取：一律基于 ParseResult 的 markdown。

        解析模式（pipeline / vlm）由配置的 parse 段决定；
        无 MinerU 可用或解析失败时按失败返回，不回退 OCR/VLM。
        """
        processing_start = datetime.now()

        try:
            parse_section = configuration.get("parse") or {}
            logger.info(
                f"使用配置 [{configuration.get('name')}] 处理文档，"
                f"解析模式: {parse_section.get('model_version', 'pipeline')}"
            )

            from services.parse_service import ensure_parse_result

            parse_data = await ensure_parse_result(
                document_id=document_id,
                file_path=file_path,
                tenant_id=tenant_id,
                parse_section=parse_section,
            )
            if not parse_data or not parse_data.get("markdown"):
                raise WorkflowError(
                    WorkflowErrorType.EXTRACT_FAILED,
                    "无法获得解析结果：请检查 MinerU 配置（MINERU_API_KEY）或文档是否可解析",
                )

            return await self._extract_from_parse(
                document_id=document_id,
                configuration=configuration,
                parse_data=parse_data,
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
        """以 ParseResult 的 markdown 作为 LLM 输入执行一次抽取。"""
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
            processing_time=processing_time,
            template_id=configuration.get("id"),
            template_name=configuration.get("name"),
        )
        return result



# 单例工作流
document_workflow = DocumentWorkflow()
