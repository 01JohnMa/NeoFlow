# services/job_runner.py
"""唯一 Job 执行 Seam：按 Configuration Type 分发 handler。

调用方（worker / API）只需调用 JobRunner.run(job)：
1. 若 job 固定了 configuration_revision_id，加载 Revision 与其 Configuration；
2. 按 Configuration.type 选择 handler；
3. 两者都无：fail-closed 拒绝。

新增能力只需注册一个 handler，不需要改路由或 worker。
"""

from typing import Any, Awaitable, Callable, Dict, Optional

from loguru import logger

from services.configuration_service import configuration_service

JobHandler = Callable[..., Awaitable[Any]]

EXTRACT_CONFIGURATION_TYPE = "extract"
PARSE_CONFIGURATION_TYPE = "parse"
CLASSIFY_CONFIGURATION_TYPE = "classify"
SPLIT_CONFIGURATION_TYPE = "split"


def _default_handlers() -> Dict[str, JobHandler]:
    """内置 handler 注册表（parse handler 延迟导入，避免加载解析依赖）。"""
    from services.parse_service import handle_parse_job

    return {
        EXTRACT_CONFIGURATION_TYPE: handle_extract_job,
        PARSE_CONFIGURATION_TYPE: handle_parse_job,
        CLASSIFY_CONFIGURATION_TYPE: handle_classify_job,
        SPLIT_CONFIGURATION_TYPE: handle_split_job,
    }


class JobRunnerError(Exception):
    """Job 无法分发或执行。"""


async def handle_extract_job(
    job: Dict[str, Any],
    revision: Optional[Dict[str, Any]] = None,
    configuration: Optional[Dict[str, Any]] = None,
) -> Any:
    """extract handler：委托给 services.extract_service（#32 v3.1 / ADR-0009）。"""
    from services.extract_service import handle_extract_job as _handle_extract_job

    return await _handle_extract_job(job, revision, configuration)


async def _handle_parse_result_capability(
    *,
    kind: str,
    job: Dict[str, Any],
    revision: Optional[Dict[str, Any]],
    configuration: Optional[Dict[str, Any]],
) -> Any:
    from agents.workflow import document_workflow
    from api.jobs import update_job
    from services.classify_split_service import run_classify, run_split
    from services.result_service import result_service

    job_id = str(job.get("job_id"))
    tenant_id = job.get("tenant_id")
    if not tenant_id:
        await update_job(job_id, "failed", error="任务缺少 tenant_id")
        return None
    document_ids = job.get("document_ids") or []
    if not document_ids:
        await update_job(job_id, "failed", error="任务缺少 document_ids")
        return None

    document_id = document_ids[0]
    parse_row = await result_service.get_document_parse_result(
        document_id, tenant_id=tenant_id
    )
    if not parse_row:
        await update_job(job_id, "failed", error="ParseResult 不存在")
        return None

    definition = (revision or {}).get("definition") or {}
    section = definition.get(kind) or {}
    await update_job(job_id, "llm")
    try:
        runner = run_classify if kind == CLASSIFY_CONFIGURATION_TYPE else run_split
        result = await runner(
            parse_data=parse_row.get("data") or {},
            definition=section,
            llm_invoke=document_workflow._llm_invoke_with_retry,
        )
        row = result_service.build_result_row(
            tenant_id=tenant_id,
            document_id=document_id,
            data=result,
            job_id=job_id,
            config_revision_id=job.get("configuration_revision_id"),
        )
        stored = await result_service.create_result(row)
        if not stored:
            await update_job(job_id, "failed", error=f"{kind} Result 写入失败")
            return None
        await update_job(job_id, "completed")
        return result
    except Exception as exc:
        logger.exception(f"{kind} Job 执行失败: job_id={job_id}")
        await update_job(job_id, "failed", error=str(exc))
        return None


async def handle_classify_job(
    job: Dict[str, Any],
    revision: Optional[Dict[str, Any]] = None,
    configuration: Optional[Dict[str, Any]] = None,
) -> Any:
    return await _handle_parse_result_capability(
        kind=CLASSIFY_CONFIGURATION_TYPE,
        job=job,
        revision=revision,
        configuration=configuration,
    )


async def handle_split_job(
    job: Dict[str, Any],
    revision: Optional[Dict[str, Any]] = None,
    configuration: Optional[Dict[str, Any]] = None,
) -> Any:
    return await _handle_parse_result_capability(
        kind=SPLIT_CONFIGURATION_TYPE,
        job=job,
        revision=revision,
        configuration=configuration,
    )


class JobRunner:
    """按 Configuration Type 分发 handler 的执行入口。"""

    def __init__(self, handlers: Optional[Dict[str, JobHandler]] = None):
        if handlers is None:
            handlers = _default_handlers()
        self._handlers: Dict[str, JobHandler] = dict(handlers)

    def register(self, configuration_type: str, handler: JobHandler) -> None:
        """注册/覆盖某个 Configuration Type 的 handler。"""
        self._handlers[configuration_type] = handler

    @property
    def handlers(self) -> Dict[str, JobHandler]:
        return dict(self._handlers)

    async def _resolve_dispatch(
        self,
        job: Dict[str, Any],
    ) -> tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """判别执行定义（fail-closed）：

        1. execution_spec：参数化能力（ADR-0007），无 Configuration Revision
        2. configuration_revision_id：按 Revision 所属 Configuration.type
        3. 两者都无：拒绝——来源不明的历史 Job 不得回落旧抽取路径
        """
        spec = job.get("execution_spec")
        if isinstance(spec, dict) and spec:
            capability = spec.get("capability")
            if not capability:
                raise JobRunnerError("execution_spec 缺少 capability")
            return str(capability), None, None

        revision_id = job.get("configuration_revision_id")
        if not revision_id:
            raise JobRunnerError(
                "Job 缺少执行定义（execution_spec 与 configuration_revision_id 均缺失）"
            )

        revision = await configuration_service.get_revision(str(revision_id))
        if not revision:
            raise JobRunnerError(f"Configuration Revision 不存在: {revision_id}")

        configuration = await configuration_service.get_configuration(
            revision["configuration_id"]
        )
        if not configuration:
            raise JobRunnerError(
                f"Configuration 不存在: {revision['configuration_id']}"
            )

        return configuration.get("type"), revision, configuration

    async def run(self, job: Dict[str, Any]) -> Any:
        """判别执行定义并分发到对应 handler。"""
        execution_type, revision, configuration = await self._resolve_dispatch(job)

        handler = self._handlers.get(execution_type)
        if handler is None:
            raise JobRunnerError(f"未注册的执行能力: {execution_type}")

        logger.info(
            f"JobRunner 分发: job_id={job.get('job_id')} "
            f"capability={execution_type} "
            f"revision={job.get('configuration_revision_id') or 'none'}"
        )
        return await handler(job=job, revision=revision, configuration=configuration)


# 单例执行入口
job_runner = JobRunner()
