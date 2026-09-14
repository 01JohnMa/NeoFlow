# agents package
"""agents 包采用惰性导出：导入 agents.json_cleaner 等轻量模块时，
不会连带拉起重依赖（langchain/langgraph）。"""

__all__ = [
    "document_workflow",
    "DocumentWorkflow",
    "WorkflowError",
    "WorkflowErrorType",
    "parse_llm_json",
    "build_error",
    "build_single_success",
]

_LAZY_EXPORTS = {
    "document_workflow": (".workflow", "document_workflow"),
    "DocumentWorkflow": (".workflow", "DocumentWorkflow"),
    "WorkflowError": (".exceptions", "WorkflowError"),
    "WorkflowErrorType": (".exceptions", "WorkflowErrorType"),
    "parse_llm_json": (".json_cleaner", "parse_llm_json"),
    "build_error": (".result_builder", "build_error"),
    "build_single_success": (".result_builder", "build_single_success"),
}


def __getattr__(name):
    if name in _LAZY_EXPORTS:
        module_name, attribute = _LAZY_EXPORTS[name]
        import importlib

        module = importlib.import_module(module_name, __name__)
        return getattr(module, attribute)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
