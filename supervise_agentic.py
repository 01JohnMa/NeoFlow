"""
ocrt提取助手 - 基于 LangGraph + paddleocr 的真实ocr系统
1. 文档分类
2. 根据文档分类指定对应的promp提取对应的字段  
3. 将对应的字段存到数据库当中
"""
from text_pipline_ocr import ocr_process
from prompt_config import *
import json
import asyncio
from typing import TypedDict, Annotated
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import InMemorySaver
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()
# 定义状态结构
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_query: str        # 用户查询
    tool_results: str    # 工具搜索结果
    final_answer: str      # 最终答案
    step: str             # 当前步骤
    
# 初始化模型
llm = ChatOpenAI(
    model=os.getenv("LLM_MODEL_ID", "gpt-4o-mini"),
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
    temperature=0.7,
)

def doc_classify_node(state:AgentState):

   ocrResult =""      
   for msg in reversed(state["messages"]):
               if isinstance(msg,HumanMessage):
                  ocrResult = msg.content          
   ocr_llm_result = llm.invoke(DOC_CLASSIFY_PROMPT.format(ocr_result=ocrResult))  
   data = json.loads(ocr_llm_result.content)
   doc_type = data["文档类型"]
   return {
      "tool_results":doc_type,
      "messages":[AIMessage(content=f"文档分类已经完成：{ocr_llm_result}")],
      "step":"classfied"
   }  

def extract_node(state:doc_classify_node)->str:
    doc_type= state["tool_results"]
    print(doc_type)
    if doc_type == "测试单":
        final_result = llm.invoke(TEXTREPORTPROMPT)
    elif doc_type == "快递单":
        final_result = llm.invoke(EXPRESS_PROMPT)
    elif doc_type == "抽样单":
        final_result = llm.invoke(SAMPLING_FORM_PROMPT)
    else:
        final_result = "未知文档类型"
    return{
        "tool_results":final_result.content,
        "step": "completed",
        "messags": [AIMessage(content=f"字段提取完成:{final_result.content}")]
    }
   # 构建工作流
def create_ocr_assitant():
    workflow = StateGraph(AgentState)
    workflow.add_node("doc_classify",doc_classify_node)
    workflow.add_node("extract",extract_node)
    
    workflow.add_edge(START,"doc_classify")
    workflow.add_edge("doc_classify","extract")
    workflow.add_edge("extract",END)
    
    #编译图
    memory = InMemorySaver()
    app = workflow.compile(checkpointer=memory)
    return app

async def main():
    app = create_ocr_assitant()
    try:
      ocrResult = ocr_process()
    except Exception as e:
        print("ocr识别失败")
    initial_state = {
        "message":[HumanMessage(content=ocrResult)],
        "step":"start"
    }
    # 配置（可选，用于记忆）
    config = {"configurable": {"thread_id": "session-1"}}
    async for output in app.astream(initial_state, config=config):
        for node_name, node_output in output.items():
            print(f"节点 {node_name} 执行完成")
            print(f"输出: {node_output}")

    
    
    