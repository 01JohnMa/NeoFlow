# services/parse_request_service.py
"""Parse 受理服务：参数规范化、请求指纹、执行规格与受理 RPC 封装。

设计要点（ADR-0007、issue #30 v3.2）：
- Parse 是参数化能力：每次提交冻结一份执行规格（execution_spec），
  Job 不再固定 Configuration Revision；
- 请求指纹只包含规范化后的原始意图（文档集合、模式、页范围），
  不注入随部署变化的默认值，保证同 Key 重试跨部署仍可命中；
- 执行等价比较使用冻结后的完整规格（由受理 RPC 比对 request_payload）。
"""

import hashlib
import json
import re
from typing import Any, Dict, List, Optional

from loguru import logger

from config.settings import settings
from services.base import SupabaseClientMixin
from services.configuration_service import PARSE_DEFAULTS

PARSE_CAPABILITY = "parse"
PARSE_SPEC_VERSION = "1"
SUPPORTED_PARSE_MODES = ("pipeline", "vlm")
DEFAULT_PARSE_MODE = "pipeline"
MAX_WATERMARK_KEYWORDS = 20
# MinerU language 取值参考（托管 API v4）：独立语言包 + 语系包
SUPPORTED_LANGUAGES = (
    "ch",
    "ch_server",
    "en",
    "japan",
    "korean",
    "chinese_cht",
    "ta",
    "te",
    "ka",
    "el",
    "th",
    "latin",
    "arabic",
    "cyrillic",
    "east_slavic",
    "devanagari",
)

_RANGE_PATTERN = re.compile(r"^(\d+)(?:-(\d+))?$")
_COMPACT_RANGES_PATTERN = re.compile(r"^\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*$")


class ParseRequestError(Exception):
    """受理前的参数错误（映射为 422）。"""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


def normalize_target_pages(raw: Optional[str]) -> Optional[List[int]]:
    """把 "1,3,5-10" 规范化为升序去重的页号列表；None/空 表示全部页面。

    规则（v3.1）：正整数、闭区间、1-based；逆序/非正数/未知格式直接拒绝；
    展开后规模受 PARSE_MAX_TARGET_PAGES 限制。
    """
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None

    pages: set[int] = set()
    for part in text.split(","):
        token = part.strip()
        match = _RANGE_PATTERN.match(token)
        if not match:
            raise ParseRequestError("invalid_target_pages", f"无法解析的页码范围: {token}")
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start
        if start < 1 or end < 1:
            raise ParseRequestError("invalid_target_pages", f"页码必须从 1 开始: {token}")
        if end < start:
            raise ParseRequestError("invalid_target_pages", f"区间顺序非法: {token}")
        if end - start + 1 > settings.PARSE_MAX_TARGET_PAGES:
            raise ParseRequestError("invalid_target_pages", f"区间过大: {token}")
        pages.update(range(start, end + 1))
        if len(pages) > settings.PARSE_MAX_TARGET_PAGES:
            raise ParseRequestError(
                "invalid_target_pages",
                f"目标页数超过上限 {settings.PARSE_MAX_TARGET_PAGES}",
            )

    if not pages:
        return None
    return sorted(pages)


def compact_target_pages(pages: Optional[List[int]]) -> Optional[str]:
    """把页号列表压缩为解析器可用的紧凑写法（1,3,5-10）。"""
    if not pages:
        return None
    ordered = sorted(set(pages))
    parts: List[str] = []
    start = prev = ordered[0]
    for page in ordered[1:]:
        if page == prev + 1:
            prev = page
            continue
        parts.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = page
    parts.append(str(start) if start == prev else f"{start}-{prev}")
    return ",".join(parts)


def resolve_parse_mode(parse_mode: Optional[str]) -> str:
    """显式模式优先；缺省取策略默认（本轮 pipeline）。"""
    if parse_mode is None:
        return DEFAULT_PARSE_MODE
    if parse_mode not in SUPPORTED_PARSE_MODES:
        raise ParseRequestError("unsupported_parse_mode", f"不支持的解析模式: {parse_mode}")
    return parse_mode


def normalize_parse_options(
    *,
    language: Optional[str] = None,
    enable_formula: Optional[bool] = None,
    enable_table: Optional[bool] = None,
    remove_watermark: Optional[bool] = None,
    watermark_keywords: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """规范化可选的 MinerU 解析参数；只保留显式提供的项（缺省不注入）。"""
    options: Dict[str, Any] = {}
    if language is not None:
        value = language.strip()
        if value not in SUPPORTED_LANGUAGES:
            raise ParseRequestError("unsupported_language", f"不支持的解析语言: {language}")
        options["language"] = value
    if enable_formula is not None:
        options["enable_formula"] = bool(enable_formula)
    if enable_table is not None:
        options["enable_table"] = bool(enable_table)
    if remove_watermark is not None:
        options["remove_watermark"] = bool(remove_watermark)
    if watermark_keywords:
        cleaned: List[str] = []
        for keyword in watermark_keywords:
            value = str(keyword).strip()
            if value and value not in cleaned:
                cleaned.append(value)
        if len(cleaned) > MAX_WATERMARK_KEYWORDS:
            raise ParseRequestError(
                "too_many_watermark_keywords",
                f"水印关键词最多 {MAX_WATERMARK_KEYWORDS} 个",
            )
        if cleaned:
            options["watermark_keywords"] = cleaned
    return options


def build_execution_spec(
    *,
    parse_mode: str,
    target_pages: Optional[List[int]],
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """冻结本次执行的完整规格：默认值在此解析，worker 只读不再回退默认。"""
    effective_params = dict(PARSE_DEFAULTS)
    for key, value in (options or {}).items():
        if value is not None:
            effective_params[key] = value
    effective_params["model_version"] = parse_mode
    effective_params["page_ranges"] = compact_target_pages(target_pages)

    return {
        "capability": PARSE_CAPABILITY,
        "spec_version": PARSE_SPEC_VERSION,
        "input_selection": {"target_pages": target_pages},
        "effective_params": effective_params,
        "policy_version": settings.PARSE_POLICY_VERSION,
    }


def build_request_fingerprint(
    *,
    document_ids: List[str],
    requested_mode: Optional[str],
    target_pages: Optional[List[int]],
    options: Optional[Dict[str, Any]] = None,
) -> str:
    """请求指纹：规范化原始意图；不含默认值等随部署变化的内容。

    可选参数仅在调用方显式提供时纳入，未提供时不改变指纹形态，
    保证与旧提交的幂等重放兼容。
    """
    intent: Dict[str, Any] = {
        "capability": PARSE_CAPABILITY,
        "spec_version": PARSE_SPEC_VERSION,
        "document_ids": sorted(set(document_ids)),
        "parse_mode": requested_mode,
        "target_pages": target_pages,
    }
    for key, value in (options or {}).items():
        if value is not None:
            intent[key] = value
    canonical = json.dumps(intent, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_document_ids(document_ids: List[str]) -> List[str]:
    """去重并保持稳定顺序（按字符串排序），保证请求指纹可复现。"""
    cleaned = [str(doc_id).strip() for doc_id in document_ids if str(doc_id).strip()]
    if not cleaned:
        raise ParseRequestError("document_ids_empty", "至少需要一个文档")
    if len(cleaned) > settings.PARSE_MAX_FILES_PER_REQUEST:
        raise ParseRequestError(
            "max_files_per_request",
            f"单次提交最多 {settings.PARSE_MAX_FILES_PER_REQUEST} 个文档",
        )
    return sorted(set(cleaned))


class ParseRequestService(SupabaseClientMixin):
    """受理封装：构建规格与指纹，调用 admit_parse_request 原子命令。"""

    _instance: Optional["ParseRequestService"] = None
    _client = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def admit(
        self,
        *,
        tenant_id: str,
        requester_id: str,
        is_admin: bool,
        document_ids: List[str],
        parse_mode: Optional[str],
        target_pages: Optional[List[int]],
        idempotency_key: Optional[str],
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """调用 admit_parse_request；返回 {status, request_id, job_ids, reason}。"""
        mode = resolve_parse_mode(parse_mode)
        spec = build_execution_spec(parse_mode=mode, target_pages=target_pages, options=options)
        fingerprint = build_request_fingerprint(
            document_ids=document_ids,
            requested_mode=parse_mode,
            target_pages=target_pages,
            options=options,
        )

        payload = {
            "p_tenant_id": tenant_id,
            "p_requester_id": requester_id,
            "p_is_admin": bool(is_admin),
            "p_document_ids": document_ids,
            "p_spec": spec,
            "p_idempotency_key": idempotency_key,
            "p_request_fingerprint": fingerprint,
            "p_policy_version": settings.PARSE_POLICY_VERSION,
            "p_max_files": settings.PARSE_MAX_FILES_PER_REQUEST,
            "p_max_active_jobs": settings.PARSE_MAX_ACTIVE_JOBS_PER_TENANT,
        }

        try:
            result = await self._run_sync(
                lambda: self._get_client().rpc("admit_parse_request", payload).execute()
            )
        except Exception as exc:
            logger.opt(exception=exc).error("Parse 受理失败")
            raise

        rows = result.data if isinstance(result.data, list) else [result.data]
        row = (rows or [{}])[0] or {}
        return {
            "status": row.get("out_status"),
            "request_id": row.get("out_request_id"),
            "job_ids": row.get("out_job_ids") or [],
            "reason": row.get("out_reason"),
        }


parse_request_service = ParseRequestService()
