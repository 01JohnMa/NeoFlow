# services/parser_adapter.py
"""ParserAdapter 接口 - 所有解析后端实现同一 ParseResult 契约。

当前接入 MinerU 托管 API（mineru-api）。
本地 4090 的 MinerU hybrid-engine / hybrid-http-client 作为后续后端：
只需注册新的 adapter 工厂，下游继续只认 ParseResult。

后端通过 Configuration definition.parse.backend 选择，
未注册的后端给出明确错误，不做静默降级。
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional

from services.parse_result import ParseResult

DEFAULT_PARSER_BACKEND = "mineru-api"

# 预留：本地 MinerU 部署（#8 范围外，后续接入）
RESERVED_LOCAL_BACKENDS = ("mineru-local", "hybrid-engine", "hybrid-http-client")


class ParserAdapterError(Exception):
    """解析适配层异常（配置错误、后端不可用、输出不可解析）。"""


class ParserAdapter(ABC):
    """解析后端接口：把文件归一化为 ParseResult。"""

    name: str = "parser"

    @abstractmethod
    async def parse(
        self,
        file_path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> ParseResult:
        """解析本地文件，返回统一 ParseResult。"""
        raise NotImplementedError


_ADAPTER_FACTORIES: Dict[str, Callable[[], ParserAdapter]] = {}


def register_parser_adapter(backend: str, factory: Callable[[], ParserAdapter]) -> None:
    """注册/覆盖某个后端名的 adapter 工厂。"""
    _ADAPTER_FACTORIES[backend] = factory


def _mineru_api_factory() -> ParserAdapter:
    from services.mineru_adapter import MinerUApiAdapter

    return MinerUApiAdapter()


register_parser_adapter("mineru-api", _mineru_api_factory)


def get_parser_adapter(params: Optional[Dict[str, Any]] = None) -> ParserAdapter:
    """按 backend 参数选择 adapter；未知/未接入后端直接报错。"""
    backend = str((params or {}).get("backend") or DEFAULT_PARSER_BACKEND)
    if backend in RESERVED_LOCAL_BACKENDS:
        raise ParserAdapterError(
            f"本地 MinerU 后端尚未接入: {backend}（当前先走 mineru-api 托管 API）"
        )

    factory = _ADAPTER_FACTORIES.get(backend)
    if factory is None:
        raise ParserAdapterError(f"不支持的 Parser 后端: {backend}")
    return factory()
