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
from config.prompts import DOC_CLASSIFY_PROMPT
from services.ocr_service import ocr_service
from services.template_service import template_service


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
    tenant_id: Optional[str]  # 租户ID，用于查询模板配置


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
        """字段提取节点 - 从数据库获取模板配置构建 prompt"""
        try:
            doc_type = state.get("document_type", "")
            ocr_text = state.get("ocr_text", "")
            tenant_id = state.get("tenant_id")
            
            logger.info(f"开始字段提取，文档类型: {doc_type}, 租户: {tenant_id}")
            
            # 检查必要参数
            if not tenant_id:
                logger.error(f"字段提取失败: 文档 {state.get('document_id')} 缺少租户ID，请确保用户已选择所属部门")
                return {
                    "extraction_data": {},
                    "step": "extract_failed",
                    "error": "缺少租户ID，用户未选择所属部门",
                    "messages": [AIMessage(content="缺少租户ID，无法获取模板配置")]
                }
            
            if not doc_type:
                return {
                    "extraction_data": {"error": "缺少文档类型"},
                    "step": "extract_failed",
                    "messages": [AIMessage(content="缺少文档类型，无法获取模板配置")]
                }
            
            # 从数据库获取模板配置
            template = await template_service.get_template_by_code(tenant_id, doc_type)
            if not template:
                return {
                    "extraction_data": {"error": f"未找到模板配置: {doc_type}"},
                    "step": "extract_failed",
                    "messages": [AIMessage(content=f"未找到文档类型 [{doc_type}] 的模板配置")]
                }
            
            # 构建 prompt 并提取
            prompt = template_service.build_extraction_prompt(template, ocr_text)
            logger.info(f"使用数据库模板 [{template.get('name')}] 构建 prompt")
            
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
            return "检测报告"
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
    
    async def process(
        self, 
        document_id: str, 
        file_path: str,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """执行工作流 - 主入口（自动分类模式）
        
        Args:
            document_id: 文档ID
            file_path: 文件路径
            tenant_id: 租户ID（可选，用于从数据库获取模板配置）
            
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
            "processing_start": processing_start,
            "tenant_id": tenant_id
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
    
    async def process_with_text(
        self, 
        document_id: str, 
        ocr_text: str,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """使用已有OCR文本执行工作流（跳过OCR步骤）
        
        用于已经完成OCR的场景，直接进行分类和提取
        
        Args:
            document_id: 文档ID
            ocr_text: OCR提取的文本
            tenant_id: 租户ID（可选，用于从数据库获取模板配置）
            
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
            "processing_start": processing_start,
            "tenant_id": tenant_id
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


    # ============ 模板化提取方法 ============
    
    async def process_with_template(
        self, 
        document_id: str, 
        file_path: str, 
        template_id: str,
        tenant_id: str
    ) -> Dict[str, Any]:
        """使用模板配置执行工作流
        
        Args:
            document_id: 文档ID
            file_path: 文件路径
            template_id: 模板ID
            tenant_id: 租户ID
            
        Returns:
            处理结果字典
        """
        processing_start = datetime.now()
        
        try:
            # 1. 获取模板配置
            template = await template_service.get_template_with_details(template_id)
            if not template:
                return {
                    "success": False,
                    "document_id": document_id,
                    "error": f"模板不存在: {template_id}"
                }
            
            logger.info(f"使用模板 [{template['name']}] 处理文档")
            
            # 2. OCR 提取
            logger.info(f"开始OCR处理: {file_path}")
            ocr_result = await ocr_service.process_document(file_path)
            ocr_text = ocr_result["text"]
            ocr_confidence = ocr_result["confidence"]
            logger.info(f"OCR完成，提取{ocr_result['total_lines']}行，置信度{ocr_confidence:.2f}")
            
            # 3. 使用模板动态构建 Prompt 并提取
            prompt = template_service.build_extraction_prompt(template, ocr_text)
            response = await self.llm.ainvoke(prompt)
            
            # 4. 解析结果
            try:
                extraction_data = json.loads(response.content)
            except json.JSONDecodeError:
                extraction_data = self._clean_json_response(response.content)
            
            processing_time = (datetime.now() - processing_start).total_seconds()
            
            logger.info(f"模板化提取完成: {len(extraction_data)}个字段，耗时{processing_time:.2f}s")
            
            return {
                "success": True,
                "document_id": document_id,
                "template_id": template_id,
                "template_name": template.get("name"),
                "document_type": template.get("code"),  # 使用模板 code 作为文档类型（解耦）
                "extraction_data": extraction_data,
                "ocr_text": ocr_text[:500] + "..." if len(ocr_text) > 500 else ocr_text,
                "ocr_confidence": ocr_confidence,
                "processing_time": processing_time,
                "step": "completed",
                "error": None
            }
            
        except Exception as e:
            logger.error(f"模板化处理失败: {e}")
            return {
                "success": False,
                "document_id": document_id,
                "error": str(e),
                "processing_time": (datetime.now() - processing_start).total_seconds()
            }
    
    async def process_merge(
        self, 
        document_id: str, 
        files: list,  # [{file_path, doc_type}, ...]
        template_id: str,
        tenant_id: str
    ) -> Dict[str, Any]:
        """Merge 模式处理：多份文档分别提取后合并
        
        用于照明事业部等场景：上传积分球+光分布两份文档，
        分别用各自的子模板提取，然后合并结果。
        
        Args:
            document_id: 文档ID
            files: 文件列表，每项包含 file_path 和 doc_type
            template_id: 合并模板ID（process_mode='merge'）
            tenant_id: 租户ID
            
        Returns:
            合并后的处理结果
        """
        processing_start = datetime.now()
        
        try:
            # 1. 获取合并模板配置
            template = await template_service.get_merge_template_info(template_id)
            if not template:
                return {
                    "success": False,
                    "document_id": document_id,
                    "error": f"模板不存在: {template_id}"
                }
            
            if template.get("process_mode") != "merge":
                return {
                    "success": False,
                    "document_id": document_id,
                    "error": f"模板 {template['name']} 不是合并模式"
                }
            
            logger.info(f"使用合并模板 [{template['name']}] 处理 {len(files)} 份文档")
            
            # 2. 获取合并规则和子模板
            merge_rule = await template_service.get_merge_rule(template_id)
            if not merge_rule:
                return {
                    "success": False,
                    "document_id": document_id,
                    "error": "合并规则配置缺失"
                }
            
            sub_template_a = template.get("sub_template_a")
            sub_template_b = template.get("sub_template_b")
            
            # 3. 分别处理每份文档
            result_a = None
            result_b = None
            ocr_texts = []
            
            for file_info in files:
                file_path = file_info.get("file_path")
                doc_type = file_info.get("doc_type", "")
                
                if not file_path:
                    continue
                
                # OCR 提取
                logger.info(f"OCR处理文档: {file_path} (类型: {doc_type})")
                ocr_result = await ocr_service.process_document(file_path)
                ocr_text = ocr_result["text"]
                ocr_texts.append(ocr_text)
                
                # 根据文档类型选择子模板
                if doc_type == merge_rule.get("doc_type_a") and sub_template_a:
                    prompt = template_service.build_extraction_prompt(sub_template_a, ocr_text)
                    response = await self.llm.ainvoke(prompt)
                    try:
                        result_a = json.loads(response.content)
                    except json.JSONDecodeError:
                        result_a = self._clean_json_response(response.content)
                    logger.info(f"文档A ({doc_type}) 提取完成: {len(result_a)}个字段")
                    
                elif doc_type == merge_rule.get("doc_type_b") and sub_template_b:
                    prompt = template_service.build_extraction_prompt(sub_template_b, ocr_text)
                    response = await self.llm.ainvoke(prompt)
                    try:
                        result_b = json.loads(response.content)
                    except json.JSONDecodeError:
                        result_b = self._clean_json_response(response.content)
                    logger.info(f"文档B ({doc_type}) 提取完成: {len(result_b)}个字段")
            
            # 4. 合并结果
            merged_data = template_service.merge_extraction_results(result_a, result_b)
            
            processing_time = (datetime.now() - processing_start).total_seconds()
            
            logger.info(f"合并提取完成: {len(merged_data)}个字段，耗时{processing_time:.2f}s")
            
            return {
                "success": True,
                "document_id": document_id,
                "template_id": template_id,
                "template_name": template.get("name"),
                "document_type": template.get("code"),  # 使用模板 code 作为文档类型（解耦）
                "extraction_data": merged_data,
                "sub_results": {
                    "result_a": result_a,
                    "result_b": result_b
                },
                "processing_time": processing_time,
                "step": "completed",
                "error": None
            }
            
        except Exception as e:
            logger.error(f"合并处理失败: {e}")
            return {
                "success": False,
                "document_id": document_id,
                "error": str(e),
                "processing_time": (datetime.now() - processing_start).total_seconds()
            }
    
    async def process_auto(
        self,
        document_id: str,
        files: list,  # [{file_path, doc_type?}, ...]
        template_id: str,
        tenant_id: str
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
            
        Returns:
            处理结果字典
        """
        try:
            # 1. 获取模板信息
            template = await template_service.get_template(template_id)
            if not template:
                return {
                    "success": False,
                    "document_id": document_id,
                    "error": f"模板不存在: {template_id}"
                }
            
            process_mode = template.get("process_mode", "single")
            logger.info(f"统一处理入口: 模板={template.get('name')}, 模式={process_mode}, 文件数={len(files)}")
            
            # 2. 根据 process_mode 选择处理方式
            if process_mode == "merge":
                # 合并模式：多文档分别提取后合并
                return await self.process_merge(
                    document_id=document_id,
                    files=files,
                    template_id=template_id,
                    tenant_id=tenant_id
                )
            else:
                # 单文档模式
                if not files:
                    return {
                        "success": False,
                        "document_id": document_id,
                        "error": "文件列表为空"
                    }
                
                file_path = files[0].get("file_path")
                if not file_path:
                    return {
                        "success": False,
                        "document_id": document_id,
                        "error": "文件路径为空"
                    }
                
                return await self.process_with_template(
                    document_id=document_id,
                    file_path=file_path,
                    template_id=template_id,
                    tenant_id=tenant_id
                )
                
        except Exception as e:
            logger.error(f"统一处理入口失败: {e}")
            return {
                "success": False,
                "document_id": document_id,
                "error": str(e)
            }
    
    async def extract_with_prompt(
        self, 
        ocr_text: str, 
        prompt_template: str
    ) -> Dict[str, Any]:
        """使用指定 Prompt 模板提取字段（底层方法）
        
        Args:
            ocr_text: OCR 文本
            prompt_template: Prompt 模板（已包含字段定义和示例）
            
        Returns:
            提取的字段字典
        """
        try:
            response = await self.llm.ainvoke(prompt_template)
            
            try:
                return json.loads(response.content)
            except json.JSONDecodeError:
                return self._clean_json_response(response.content)
                
        except Exception as e:
            logger.error(f"字段提取失败: {e}")
            return {"error": str(e)}


# 单例工作流
ocr_workflow = OCRWorkflow()

