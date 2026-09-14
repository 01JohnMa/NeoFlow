"""Document analysis agent."""

from typing import Any, Dict, List

from sdk.models import DocumentAnalysis, SDKModelProfile
from sdk.openai_agents_runtime import run_structured_agent


DOC_ANALYZER_INSTRUCTIONS = """你是文档模板分析专家。
根据文档解析后的 markdown、文件名和已有部门列表，推断文档类型、所属部门、可提取字段和 few-shot 示例。
字段 key 必须是蛇形英文；字段类型只能使用 text/date/number；不要编造解析文本中没有依据的样例值。"""


async def analyze_document(
    *,
    parse_text: str,
    file_name: str,
    tenants: List[Dict[str, Any]],
    model_profile: SDKModelProfile | None = None,
) -> DocumentAnalysis:
    prompt = (
        f"文件名: {file_name}\n\n"
        f"已有部门列表: {tenants}\n\n"
        f"文档解析 markdown:\n{parse_text}"
    )
    result = await run_structured_agent(
        name="doc_analyzer_agent",
        instructions=DOC_ANALYZER_INSTRUCTIONS,
        prompt=prompt,
        output_type=DocumentAnalysis,
        model_profile=model_profile,
    )
    if isinstance(result, DocumentAnalysis):
        return result
    return DocumentAnalysis.model_validate(result)
