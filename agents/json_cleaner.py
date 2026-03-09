# agents/json_cleaner.py
"""LLM JSON 响应解析与清洗"""

import json
from typing import Optional


def parse_llm_json(content: str) -> dict:
    """解析 LLM 返回的 JSON，自动清洗 Markdown 代码块等噪音。

    处理顺序：
    1. 直接尝试解析
    2. 剥除 ```json ... ``` 或 ``` ... ``` 包裹
    3. 提取第一个 { ... } 片段再解析
    4. 以上均失败时返回 {"raw_response": content}

    Args:
        content: LLM 返回的原始字符串

    Returns:
        解析后的字典，失败时包含 raw_response 键
    """
    if not content:
        return {}

    content = content.strip()

    # 1. 直接解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 2. 剥除 Markdown 代码块
    cleaned = _strip_markdown_fence(content)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 3. 提取第一个 JSON 对象
    extracted = _extract_first_json_object(cleaned)
    if extracted:
        try:
            return json.loads(extracted)
        except json.JSONDecodeError:
            pass

    return {"raw_response": content}


def _strip_markdown_fence(content: str) -> str:
    """剥除 Markdown 代码块标记"""
    if content.startswith("```"):
        # 移除首行（```json 或 ```）
        lines = content.split("\n")
        lines = lines[1:]
        # 移除末尾 ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return content


def _extract_first_json_object(content: str) -> Optional[str]:
    """从文本中提取第一个完整的 JSON 对象"""
    start = content.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i, ch in enumerate(content[start:], start=start):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return content[start : i + 1]

    return None
