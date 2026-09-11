# services/job_runner.py
"""唯一 Job 执行 Seam：按 Configuration Type 分发 handler。

调用方（worker / API）只需调用 JobRunner.run(job)：
1. 若 job 固定了 configuration_revision_id，加载 Revision 与其 Configuration；
2. 按 Configuration.type 选择 handler；
3. 没有 Revision 的历史 job 走 extract handler（兼容旧文档处理流程）。

新增能力（如 #8 的 parse）只需注册一个 handler，不需要改路由或 worker。
"""

from typing import Any, Awaitable, Callable, Dict, Optional

from loguru import logger

from services.configuration_service import configuration_service

JobHandler = Callable[..., Awaitable[Any]]

EXTRACT_CONFIGURATION_TYPE = "extract"


class JobRunnerError(Exception):
    """Job 无法分发或执行。"""


async def handle_extract_job(
    job: Dict[str, Any],
    revision: Optional[Dict[str, Any]] = None,
    configuration: Optional[Dict[str, Any]] = None,
) -> Any:
    """extract handler：沿用现有文档抽取流程（Result + 旧业务表镜像）。"""
    from api.jobs import update_job
    from api.routes.documents.process import process_document_task
    from services.supabase_service import supabase_service

    job_id = str(job.get("job_id"))
    document_ids = job.get("document_ids") or []
    if not document_ids:
        await update_job(job_id, "failed", error="任务缺少 document_ids")
        return None

    document_id = document_ids[0]
    document = await supabase_service.get_document(document_id)
    if not document:
        await update_job(job_id, "failed", error=f"文档不存在: {document_id}")
        return None

    task_kwargs = {
        "document_id": document_id,
        "file_path": document.get("file_path", ""),
        "template_id": document.get("template_id"),
        "tenant_id": document.get("tenant_id") or job.get("tenant_id"),
        "custom_push_name": document.get("custom_push_name"),
        "job_id": job_id,
        "configuration_revision_id": job.get("configuration_revision_id"),
    }
    if job.get("job_type") == "crm":
        task_kwargs["force_pending_review"] = True

    return await process_document_task(**task_kwargs)


class JobRunner:
    """按 Configuration Type 分发 handler 的执行入口。"""

    def __init__(self, handlers: Optional[Dict[str, JobHandler]] = None):
        if handlers is None:
            handlers = {EXTRACT_CONFIGURATION_TYPE: handle_extract_job}
        self._handlers: Dict[str, JobHandler] = dict(handlers)

    def register(self, configuration_type: str, handler: JobHandler) -> None:
        """注册/覆盖某个 Configuration Type 的 handler。"""
        self._handlers[configuration_type] = handler

    @property
    def handlers(self) -> Dict[str, JobHandler]:
        return dict(self._handlers)

    async def _resolve_configuration_type(
        self,
        job: Dict[str, Any],
    ) -> tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        revision_id = job.get("configuration_revision_id")
        if not revision_id:
            # 兼容没有 Revision 的历史 job：旧文档处理统一按抽取处理
            return EXTRACT_CONFIGURATION_TYPE, None, None

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
        """加载 job 固定的 Revision 并分发到对应 handler。"""
        configuration_type, revision, configuration = await self._resolve_configuration_type(job)

        handler = self._handlers.get(configuration_type)
        if handler is None:
            raise JobRunnerError(f"未注册的 Configuration Type: {configuration_type}")

        logger.info(
            f"JobRunner 分发: job_id={job.get('job_id')} "
            f"type={configuration_type} revision={job.get('configuration_revision_id') or 'legacy'}"
        )
        return await handler(job=job, revision=revision, configuration=configuration)


# 单例执行入口
job_runner = JobRunner()
