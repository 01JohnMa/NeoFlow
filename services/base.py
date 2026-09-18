# services/base.py
"""服务层基类"""

import asyncio
from functools import partial
from typing import Any, Callable, Dict, List, Optional


class SupabaseClientMixin:
    """提供懒加载 Supabase 客户端的 Mixin，避免循环导入"""

    _client: Optional[object] = None

    def _get_client(self):
        if self._client is None:
            from services.supabase_service import supabase_service
            self._client = supabase_service.client
        return self._client

    async def _run_sync(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """将同步 I/O 卸载到线程池，避免阻塞 asyncio 事件循环。"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(fn, *args, **kwargs))


EXTRACTION_PROMPT_TEMPLATE = """你是一个专业的数据提取助手，专门处理{doc_type}的解析文本。请从用户提供的文本中精准提取以下字段。

**目标字段：**
{field_list}

**处理规则：**
1. 日期格式统一为 YYYY-MM-DD
2. 缺失字段值设为空字符串 ""
3. 数值保持原文精度，保留单位
4. 确保 JSON 语法正确（使用英文双引号、英文逗号）
5. 所有字段值必须严格来自下方文本

**输出要求：**
- 仅输出扁平的 JSON 对象，只包含上述目标字段，禁止添加任何其他字段
- 不要包含任何解释、引言或 Markdown 代码块标记

现在，请处理用户提供的解析文本：
{markdown}"""


def build_field_table(fields: List[Dict[str, Any]]) -> str:
    """
    将字段列表构建为 Markdown 表格字符串。

    供 build_extraction_prompt 使用。
    """
    field_lines = []
    for i, field in enumerate(fields, 1):
        field_key = field.get("field_key", "")
        field_label = field.get("field_label", "")
        field_type = field.get("field_type", "text")
        extraction_hint = field.get("extraction_hint", "")

        if field_type == "date":
            type_hint = "（日期格式：YYYY-MM-DD）"
        elif field_type == "number":
            type_hint = "（数值类型）"
        else:
            type_hint = ""

        hint = f"{type_hint} {extraction_hint}".strip()
        field_lines.append(f"| {i} | {field_label} | {field_key} | {hint}")

    return (
        "| 序号 | 字段含义 | JSON键名 | 说明 |\n"
        "|------|----------|----------|------|\n"
        + "\n".join(field_lines)
    )


def build_extraction_prompt(config: Dict[str, Any], markdown: str) -> str:
    """
    根据 Extraction Configuration 构建 LLM 提取 Prompt。

    Args:
        config: 归一化后的抽取配置（name / fields / extraction_prompt）
        markdown: ParseResult 的解析文本
    """
    custom_prompt = config.get("extraction_prompt")
    if custom_prompt:
        return custom_prompt.replace("{markdown}", markdown)

    return EXTRACTION_PROMPT_TEMPLATE.format(
        doc_type=config.get("name", "文档"),
        field_list=build_field_table(config.get("fields") or []),
        markdown=markdown,
    )


