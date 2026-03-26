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


def build_field_table(fields: List[Dict[str, Any]]) -> str:
    """
    将模板字段列表构建为 Markdown 表格字符串。

    供 template_service.build_extraction_prompt 和
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


def build_examples_section(examples: List[Dict[str, Any]]) -> str:
    """
    将 few-shot 示例列表构建为 Prompt 示例段落。

    供 template_service 和 vlm_service 共同使用。
    """
    if not examples:
        return ""

    section = "**参考示例：**\n"
    for i, ex in enumerate(examples, 1):
        example_input = ex.get("example_input", "").strip()
        example_output = ex.get("example_output", {})
        if isinstance(example_output, str):
            try:
                example_output = json.loads(example_output)
            except json.JSONDecodeError:
                pass
        output_str = json.dumps(example_output, ensure_ascii=False)
        section += (
            f"\n示例{i}输入文本片段：\n{example_input}\n\n"
            f"示例{i}输出：\n{output_str}\n"
        )
    return section
