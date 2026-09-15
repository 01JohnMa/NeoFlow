"""Orchestration for AI template generation sessions."""

from typing import Any, Dict

from services.configuration_service import configuration_service
from sdk.agents.doc_analyzer_agent import analyze_document as run_doc_analyzer
from sdk.agents.prompt_agent import build_fallback_prompt, generate_prompt as run_prompt_agent
from sdk.models import (
    CommitResult,
    ConfirmTemplateRequest,
    DocumentAnalysis,
    SDKModelProfile,
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
    return {
        "fields": fields,
        "extraction_prompt": prompt,
        "parse": {"model_version": session.parse_mode},
        "per_page_extraction": confirmed.per_page_extraction,
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
    async def analyze_document(
        self,
        session: SDKSession,
        parse_text: str,
        *,
        model_profile: SDKModelProfile | None = None,
    ) -> DocumentAnalysis:
        return await run_doc_analyzer(
            parse_text=parse_text,
            file_name=session.file_name,
            instruction=session.instruction,
            model_profile=model_profile,
        )

    async def generate_prompt(
        self,
        session: SDKSession,
        *,
        model_profile: SDKModelProfile | None = None,
    ) -> str:
        if not session.confirmed_template:
            raise ValueError("请先确认模板信息")
        try:
            return await run_prompt_agent(session.confirmed_template, model_profile=model_profile)
        except Exception:
            if model_profile:
                raise
            return build_fallback_prompt(session.confirmed_template)

    async def commit(self, session: SDKSession) -> CommitResult:
        if not session.confirmed_template:
            raise ValueError("请先确认模板信息")

        confirmed = session.confirmed_template
        tenant_id = session.tenant_id
        if not tenant_id:
            raise ValueError("会话缺少所属租户，请重新创建会话")

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
        )


orchestrator = SDKOrchestrator()
