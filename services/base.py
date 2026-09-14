# services/base.py
"""服务层基类"""

import asyncio
import json
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


EXTRACTION_PROMPT_TEMPLATE = """你是一个专业的数据提取助手，专门处理{doc_type}的OCR识别文本。请从用户提供的文本中精准提取以下字段。

**目标字段：**
{field_list}

**处理规则：**
1. 日期格式统一为 YYYY-MM-DD
2. 缺失字段值设为空字符串 ""
3. 数值保持原文精度，保留单位
4. 确保 JSON 语法正确（使用英文双引号、英文逗号）
5. 所有字段值必须严格来自下方文本，禁止使用或复述示例中的具体数值

{examples_section}

**输出要求：**
- 仅输出扁平的 JSON 对象，只包含上述目标字段，禁止添加任何其他字段
- 不要包含任何解释、引言或 Markdown 代码块标记

现在，请处理用户提供的OCR文本：
{ocr_text}"""


def build_field_table(fields: List[Dict[str, Any]]) -> str:
    """
    将字段列表构建为 Markdown 表格字符串。

    供 build_extraction_prompt 和
    vlm_service.build_vlm_prompt 共同使用，保持两条路径的 prompt 风格一致。
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


def build_extraction_prompt(config: Dict[str, Any], ocr_text: str) -> str:
    """
    根据 Extraction Configuration 构建 LLM 提取 Prompt。

    Args:
        config: 归一化后的抽取配置（name / fields / examples / extraction_prompt）
        ocr_text: OCR 识别文本
    """
    custom_prompt = config.get("extraction_prompt")
    if custom_prompt:
        return custom_prompt.replace("{ocr_text}", ocr_text)

    return EXTRACTION_PROMPT_TEMPLATE.format(
        doc_type=config.get("name", "文档"),
        field_list=build_field_table(config.get("fields") or []),
        examples_section=build_examples_section(config.get("examples") or []),
        ocr_text=ocr_text,
    )


def build_field_mapping(config: Dict[str, Any]) -> Dict[str, str]:
    """构建字段到飞书列名的映射：{field_key: feishu_column}。"""
    mapping: Dict[str, str] = {}
    for field in config.get("fields") or []:
        field_key = field.get("field_key")
        feishu_column = field.get("feishu_column")
        if field_key and feishu_column:
            mapping[field_key] = feishu_column
    return mapping


def build_examples_section(examples: List[Dict[str, Any]]) -> str:
    """
    将 few-shot 示例列表构建为 Prompt 示例段落。

    只展示示例输出的键结构（值用 "..." 占位），避免模型照抄示例值。
    供 build_extraction_prompt 和 vlm_service 共同使用。
    """
    if not examples:
        return ""

    section = "**参考示例（仅格式参考；值必须来自待抽取文本，禁止照抄示例）：**\n"
    for i, ex in enumerate(examples, 1):
        example_input = ex.get("example_input", "").strip()
        example_output = ex.get("example_output", {})
        if isinstance(example_output, str):
            try:
                example_output = json.loads(example_output)
            except json.JSONDecodeError:
                example_output = {}
        structure = (
            {key: "..." for key in example_output.keys()}
            if isinstance(example_output, dict)
            else {}
        )
        output_str = json.dumps(structure, ensure_ascii=False)
        section += (
            f"\n示例{i}输入文本片段：\n{example_input}\n\n"
            f"示例{i}输出结构：\n{output_str}\n"
        )
    return section
