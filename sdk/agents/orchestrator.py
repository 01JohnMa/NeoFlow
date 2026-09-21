"""Orchestration for AI template generation sessions."""

from typing import Any, Dict

from services.configuration_service import configuration_service
from services.extract_configuration import draft_fields_definition
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
    """Materialize a new confirmed proposal as schema, never as stored fields."""
    return draft_fields_definition([field.model_dump() for field in confirmed.fields], prompt)


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

        session.state = SDKSessionState.COMMITTED
        return CommitResult(
            tenant_id=tenant_id,
            configuration_id=configuration["id"],
            revision_id=None,
            revision_number=None,
            status="draft",
            field_count=len(confirmed.fields),
        )


orchestrator = SDKOrchestrator()
