"""Orchestration for AI template generation sessions."""

from typing import Any, Dict

from services.configuration_service import configuration_service
from services.tenant_service import tenant_service
from sdk.agents.code_agent import generate_cleaner_code
from sdk.agents.doc_analyzer_agent import analyze_document as run_doc_analyzer
from sdk.agents.prompt_agent import build_fallback_prompt, generate_prompt as run_prompt_agent
from sdk.models import (
    CommitResult,
    ConfirmTemplateRequest,
    DocumentAnalysis,
    SDKSession,
    SDKSessionState,
)


def build_configuration_definition(
    session: SDKSession,
    confirmed: ConfirmTemplateRequest,
    prompt: str,
) -> Dict[str, Any]:
    """把向导确认的模板草稿映射为 Configuration definition。"""
    fields = [
        {
            "field_key": field.field_key,
            "field_label": field.field_label,
            "field_type": field.field_type,
            "extraction_hint": field.extraction_hint,
            "review_enforced": field.review_enforced,
            "review_allowed_values": field.review_allowed_values,
            "sort_order": index,
        }
        for index, field in enumerate(confirmed.fields)
    ]
    examples = [
        {
            "example_input": example.example_input,
            "example_output": example.example_output,
            "sort_order": index,
            "is_active": True,
        }
        for index, example in enumerate(confirmed.examples)
    ]
    return {
        "fields": fields,
        "examples": examples,
        "extraction_prompt": prompt,
        "extraction_mode": confirmed.extraction_mode,
        "per_page_extraction": confirmed.per_page_extraction,
        "cleaner_module": None,
        "output_mode": "both" if session.excel_template_path else "bitable",
        "excel": {
            "file_name": session.excel_template_file_name,
            "path": session.excel_template_path,
            "placeholders": [
                placeholder.model_dump() for placeholder in session.excel_placeholders
            ],
        },
    }


class SDKOrchestrator:
    async def analyze_document(self, session: SDKSession) -> DocumentAnalysis:
        tenants = await tenant_service.get_all_tenants(active_only=True)
        return await run_doc_analyzer(
            ocr_text=session.ocr_text,
            file_name=session.file_name,
            tenants=tenants,
        )

    async def generate_prompt(self, session: SDKSession) -> str:
        if not session.confirmed_template:
            raise ValueError("请先确认模板信息")
        try:
            return await run_prompt_agent(session.confirmed_template)
        except Exception:
            return build_fallback_prompt(session.confirmed_template)

    async def generate_code(self, session: SDKSession) -> str:
        if not session.confirmed_template:
            raise ValueError("请先确认模板信息")
        return await generate_cleaner_code(session.confirmed_template)

    async def commit(self, session: SDKSession) -> CommitResult:
        if not session.confirmed_template:
            raise ValueError("请先确认模板信息")

        confirmed = session.confirmed_template
        tenant_id = confirmed.tenant_id
        if not tenant_id:
            if not confirmed.tenant_name or not confirmed.tenant_code:
                raise ValueError("新建部门需要 tenant_name 和 tenant_code")
            tenant = await tenant_service.create_tenant({
                "name": confirmed.tenant_name,
                "code": confirmed.tenant_code,
                "description": f"由 AI 模板向导创建：{confirmed.tenant_name}",
            })
            tenant_id = tenant["id"]

        prompt = session.prompt or build_fallback_prompt(confirmed)
        definition = build_configuration_definition(session, confirmed, prompt)

        configuration = await configuration_service.create_configuration(
            {
                "tenant_id": tenant_id,
                "name": confirmed.template_name,
                "code": confirmed.template_code,
                "description": confirmed.description,
                "type": "extract",
                "definition": definition,
            },
            created_by=session.user_id,
        )
        published = await configuration_service.publish_configuration(
            configuration["id"],
            created_by=session.user_id,
        )
        revision = published.get("revision") or {}

        session.state = SDKSessionState.COMMITTED
        return CommitResult(
            tenant_id=tenant_id,
            configuration_id=configuration["id"],
            revision_id=revision.get("id", ""),
            revision_number=revision.get("revision_number", 1),
            field_count=len(confirmed.fields),
            example_count=len(confirmed.examples),
        )


orchestrator = SDKOrchestrator()
