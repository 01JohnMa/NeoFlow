"""ParseResult-backed Classify and Split services.

Both services expose an injected LLM seam so the Job handlers can share the
platform model client while tests remain offline. Results refer back to page
blocks and never introduce business sample semantics.
"""

import json
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional

from agents.json_cleaner import parse_llm_json

LlmInvoke = Callable[[str], Awaitable[str]]


def _pages(parse_data: Dict[str, Any]) -> list[Dict[str, Any]]:
    return [page for page in (parse_data.get("pages") or []) if isinstance(page, dict)]


def _source_refs(parse_data: Dict[str, Any], page_numbers: Iterable[int]) -> list[Dict[str, Any]]:
    wanted = {int(page_no) for page_no in page_numbers}
    refs: list[Dict[str, Any]] = []
    for page in _pages(parse_data):
        page_no = page.get("page_no")
        if page_no not in wanted:
            continue
        for block in page.get("blocks") or []:
            if not isinstance(block, dict) or not block.get("id"):
                continue
            refs.append(
                {
                    "page_no": page_no,
                    "block_id": block["id"],
                    "bbox": block.get("bbox"),
                    "coordinate_space": page.get("coordinate_space", "pixel"),
                    "source": block.get("source"),
                }
            )
    return refs


def _all_page_numbers(parse_data: Dict[str, Any]) -> list[int]:
    return [int(page["page_no"]) for page in _pages(parse_data) if page.get("page_no") is not None]


def _prompt(kind: str, parse_data: Dict[str, Any], definition: Dict[str, Any]) -> str:
    return json.dumps(
        {
            "task": kind,
            "rules": definition,
            "markdown": parse_data.get("markdown") or "",
            "pages": [
                {"page_no": page.get("page_no"), "markdown": page.get("markdown") or ""}
                for page in _pages(parse_data)
            ],
            "output_rules": (
                "Return JSON only. For classify use label, confidence, reasoning, source_pages."
                if kind == "classify"
                else "Return JSON only. For split use segments[{category,pages,confidence}] and uncategorized_pages."
            ),
        },
        ensure_ascii=False,
    )


async def run_classify(
    *,
    parse_data: Dict[str, Any],
    definition: Optional[Dict[str, Any]],
    llm_invoke: LlmInvoke,
) -> Dict[str, Any]:
    """Classify a parsed document and attach page/block provenance."""
    definition = definition or {}
    payload = parse_llm_json(await llm_invoke(_prompt("classify", parse_data, definition)))
    label = payload.get("label")
    if not isinstance(label, str) or not label.strip():
        return {
            "label": definition.get("fallback_label", "unclassified"),
            "confidence": None,
            "reasoning": None,
            "source_refs": [],
        }
    source_pages = payload.get("source_pages") or []
    valid_pages = {page_no for page_no in _all_page_numbers(parse_data)}
    selected_pages = [int(page_no) for page_no in source_pages if int(page_no) in valid_pages]
    confidence = payload.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        confidence = None
    return {
        "label": label.strip(),
        "confidence": confidence,
        "reasoning": payload.get("reasoning") if isinstance(payload.get("reasoning"), str) else None,
        "source_refs": _source_refs(parse_data, selected_pages),
    }


async def run_split(
    *,
    parse_data: Dict[str, Any],
    definition: Optional[Dict[str, Any]],
    llm_invoke: LlmInvoke,
) -> Dict[str, Any]:
    """Split a parsed document into generic page segments."""
    definition = definition or {}
    payload = parse_llm_json(await llm_invoke(_prompt("split", parse_data, definition)))
    valid_pages = set(_all_page_numbers(parse_data))
    segments: list[Dict[str, Any]] = []
    assigned: set[int] = set()
    for index, raw in enumerate(payload.get("segments") or [], 1):
        if not isinstance(raw, dict) or not isinstance(raw.get("category"), str):
            continue
        pages = sorted({int(page_no) for page_no in raw.get("pages") or [] if int(page_no) in valid_pages})
        if not pages:
            continue
        assigned.update(pages)
        confidence = raw.get("confidence")
        if confidence not in {"high", "medium", "low"}:
            confidence = None
        segments.append(
            {
                "segment_id": f"segment-{index}",
                "category": raw["category"].strip(),
                "pages": pages,
                "confidence": confidence,
                "source_refs": _source_refs(parse_data, pages),
            }
        )
    reported_uncategorized = {
        int(page_no) for page_no in payload.get("uncategorized_pages") or [] if int(page_no) in valid_pages
    }
    if definition.get("allow_uncategorized", "include") == "omit":
        uncategorized = []
    else:
        uncategorized = sorted(reported_uncategorized | (valid_pages - assigned))
    return {"segments": segments, "uncategorized_pages": uncategorized}

