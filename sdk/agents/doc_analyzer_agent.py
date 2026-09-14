"""Document analysis agent."""

from sdk.models import DocumentAnalysis, SDKModelProfile
from sdk.openai_agents_runtime import run_structured_agent


DOC_ANALYZER_INSTRUCTIONS = """你是文档模板分析专家。
根据文档解析后的 markdown 与操作者说明，建议可抽取的字段（key、标签、类型、描述）。
字段 key 必须是蛇形英文；字段类型只能使用 text/date/number；描述用一句话说明取值线索。
不要推断文档类型或所属部门，也不要编造样例值。"""


async def analyze_document(
    *,
    parse_text: str,
    file_name: str,
    instruction: str | None = None,
    model_profile: SDKModelProfile | None = None,
) -> DocumentAnalysis:
    prompt = f"文件名: {file_name}\n\n"
    if instruction:
        prompt += f"操作者说明: {instruction}\n\n"
    prompt += f"文档解析 markdown:\n{parse_text}"
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
