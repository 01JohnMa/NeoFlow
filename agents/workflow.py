# agents/workflow.py
"""LangGraph OCR处理工作流 - 基于MVP代码 supervise_agentic.py 重构"""

import json
import asyncio
from typing import TypedDict, Annotated, Any, Dict, Optional
from datetime import datetime

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from loguru import logger

from config.settings import settings
from config.prompts import (
    DOC_CLASSIFY_PROMPT, 
    TEXTREPORT_PROMPT, 
    EXPRESS_PROMPT, 
    SAMPLING_FORM_PROMPT
)
from services.ocr_service import ocr_service


class WorkflowState(TypedDict):
    """工作流状态定义 - 扩展自MVP的AgentState"""
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


class OCRWorkflow:
    """OCR处理工作流 - 基于MVP代码重构"""
    
    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL_ID,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=settings.LLM_TEMPERATURE,
        )
        self.memory = MemorySaver()
        self.workflow = self._build_workflow()
    
    def _build_workflow(self) -> StateGraph:
        """构建工作流 - 对应MVP的create_ocr_assitant"""
        workflow = StateGraph(WorkflowState)
        
        # 添加节点 - 对应MVP的节点
        workflow.add_node("ocr_extract", self._ocr_node)
        workflow.add_node("doc_classify", self._classify_node)  # 对应 doc_classify_node
        workflow.add_node("extract", self._extract_node)        # 对应 extract_node
        
        # 定义边
        workflow.add_edge(START, "ocr_extract")
        workflow.add_edge("ocr_extract", "doc_classify")
        workflow.add_edge("doc_classify", "extract")
        workflow.add_edge("extract", END)
        
        return workflow.compile(checkpointer=self.memory)
    
    async def _ocr_node(self, state: WorkflowState) -> Dict[str, Any]:
        """OCR提取节点 - 新增节点，集成OCR服务"""
        try:
            file_path = state.get("file_path", "")
            if not file_path:
                return {
                    "error": "文件路径为空",
                    "step": "ocr_failed"
                }
            
            logger.info(f"开始OCR处理: {file_path}")
            
            result = await ocr_service.process_document(file_path)
            
            logger.info(f"OCR完成，提取{result['total_lines']}行，置信度{result['confidence']:.2f}")
            
            return {
                "ocr_text": result["text"],
                "ocr_confidence": result["confidence"],
                "step": "ocr_completed",
                "messages": [AIMessage(content=f"OCR提取完成，共{result['total_lines']}行文本")]
            }
            
        except Exception as e:
            logger.error(f"OCR处理失败: {e}")
            return {"error": str(e), "step": "ocr_failed"}
    
    async def _classify_node(self, state: WorkflowState) -> Dict[str, Any]:
        """文档分类节点 - 对应MVP的doc_classify_node"""
        try:
            ocr_text = state.get("ocr_text", "")
            
            if not ocr_text:
                raise ValueError("OCR文本为空，无法分类")
            
            logger.info("开始文档分类...")
            
            # 使用分类Prompt - 与MVP保持一致
            prompt = DOC_CLASSIFY_PROMPT.format(ocr_result=ocr_text[:2000])
            response = await self.llm.ainvoke(prompt)
            
            # 解析响应 - 与MVP逻辑一致
            try:
                data = json.loads(response.content)
                doc_type = data.get("文档类型", "未知")
            except json.JSONDecodeError:
                # 回退：关键词匹配
                doc_type = self._fallback_classify(ocr_text)
            
            logger.info(f"文档分类结果: {doc_type}")
            
            return {
                "document_type": doc_type,
                "step": "classified",
                "messages": [AIMessage(content=f"文档分类完成: {doc_type}")]
            }
            
        except Exception as e:
            logger.error(f"分类失败: {e}")
            return {"error": str(e), "step": "classify_failed"}
    
    async def _extract_node(self, state: WorkflowState) -> Dict[str, Any]:
        """字段提取节点 - 对应MVP的extract_node"""
        try:
            doc_type = state.get("document_type", "")
            ocr_text = state.get("ocr_text", "")
            
            logger.info(f"开始字段提取，文档类型: {doc_type}")
            
            # 根据文档类型选择Prompt - 与MVP逻辑一致
            if doc_type == "测试单":
                prompt = f"{TEXTREPORT_PROMPT}\n\nOCR文本：\n{ocr_text}"
            elif doc_type == "快递单":
                prompt = f"{EXPRESS_PROMPT}\n\nOCR文本：\n{ocr_text}"
            elif doc_type == "抽样单":
                prompt = f"{SAMPLING_FORM_PROMPT}\n\nOCR文本：\n{ocr_text}"
            else:
                return {
                    "extraction_data": {"error": f"不支持的文档类型: {doc_type}"},
                    "step": "extract_failed",
                    "messages": [AIMessage(content=f"不支持的文档类型: {doc_type}")]
                }
            
            response = await self.llm.ainvoke(prompt)
            
            # 解析JSON
            try:
                extraction_data = json.loads(response.content)
            except json.JSONDecodeError:
                # 尝试清理后解析
                extraction_data = self._clean_json_response(response.content)
            
            logger.info(f"字段提取完成: {len(extraction_data)}个字段")
            
            return {
                "extraction_data": extraction_data,
                "step": "completed",
                "messages": [AIMessage(content=f"字段提取完成: {json.dumps(extraction_data, ensure_ascii=False)[:200]}...")]
            }
            
        except Exception as e:
            logger.error(f"提取失败: {e}")
            return {"error": str(e), "step": "extract_failed"}
    
    def _fallback_classify(self, text: str) -> str:
        """关键词回退分类"""
        if any(kw in text for kw in ["运单号", "快递单号", "收件人", "寄件人", "物流"]):
            return "快递单"
        elif any(kw in text for kw in ["抽样编号", "抽样基数", "备样量", "被抽样单位"]):
            return "抽样单"
        elif any(kw in text for kw in ["检测项目", "检测结果", "检验依据", "检验结论"]):
            return "测试单"
        else:
            return "未知"
    
    def _clean_json_response(self, content: str) -> dict:
        """清理LLM响应中的JSON"""
        content = content.strip()
        # 移除可能的Markdown代码块
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        
        try:
            return json.loads(content.strip())
        except:
            return {"raw_response": content}
    
    async def process(self, document_id: str, file_path: str) -> Dict[str, Any]:
        """执行工作流 - 主入口
        
        Args:
            document_id: 文档ID
            file_path: 文件路径
            
        Returns:
            处理结果字典
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
            "processing_start": processing_start
        }
        
        config = {"configurable": {"thread_id": document_id}}
        
        try:
            final_state = await self.workflow.ainvoke(initial_state, config=config)
            
            processing_time = (datetime.now() - processing_start).total_seconds()
            
            return {
                "success": final_state.get("error") is None,
                "document_id": document_id,
                "document_type": final_state.get("document_type"),
                "extraction_data": final_state.get("extraction_data"),
                "ocr_text": final_state.get("ocr_text", "")[:500] + "...",  # 截断
                "ocr_confidence": final_state.get("ocr_confidence"),
                "processing_time": processing_time,
                "step": final_state.get("step"),
                "error": final_state.get("error")
            }
            
        except Exception as e:
            logger.error(f"工作流执行失败: {e}")
            return {
                "success": False,
                "document_id": document_id,
                "error": str(e),
                "processing_time": (datetime.now() - processing_start).total_seconds()
            }
    
    async def process_with_text(self, document_id: str, ocr_text: str) -> Dict[str, Any]:
        """使用已有OCR文本执行工作流（跳过OCR步骤）
        
        用于已经完成OCR的场景，直接进行分类和提取
        
        Args:
            document_id: 文档ID
            ocr_text: OCR提取的文本
            
        Returns:
            处理结果字典
        """
        processing_start = datetime.now()
        
        # 直接从分类节点开始
        initial_state: WorkflowState = {
            "messages": [HumanMessage(content=ocr_text)],
            "document_id": document_id,
            "file_path": "",
            "ocr_text": ocr_text,
            "ocr_confidence": 1.0,  # 假设外部OCR置信度
            "document_type": "",
            "extraction_data": {},
            "step": "ocr_completed",
            "error": None,
            "processing_start": processing_start
        }
        
        # 构建一个简化的工作流（跳过OCR）
        workflow = StateGraph(WorkflowState)
        workflow.add_node("doc_classify", self._classify_node)
        workflow.add_node("extract", self._extract_node)
        workflow.add_edge(START, "doc_classify")
        workflow.add_edge("doc_classify", "extract")
        workflow.add_edge("extract", END)
        
        compiled = workflow.compile(checkpointer=self.memory)
        config = {"configurable": {"thread_id": f"{document_id}-text"}}
        
        try:
            final_state = await compiled.ainvoke(initial_state, config=config)
            
            processing_time = (datetime.now() - processing_start).total_seconds()
            
            return {
                "success": final_state.get("error") is None,
                "document_id": document_id,
                "document_type": final_state.get("document_type"),
                "extraction_data": final_state.get("extraction_data"),
                "processing_time": processing_time,
                "step": final_state.get("step"),
                "error": final_state.get("error")
            }
            
        except Exception as e:
            logger.error(f"工作流执行失败: {e}")
            return {
                "success": False,
                "document_id": document_id,
                "error": str(e)
            }


# 单例工作流
ocr_workflow = OCRWorkflow()

