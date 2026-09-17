"""Pydantic models for the AI template generation flow."""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class SDKSessionState(str, Enum):
    PARSING = "parsing"
    PARSED = "parsed"
    PARSE_FAILED = "parse_failed"
    ANALYZED = "analyzed"
    TEMPLATE_CONFIRMED = "template_confirmed"
    PROMPT_GENERATED = "prompt_generated"
    COMMITTED = "committed"


class DetectedField(BaseModel):
    field_key: str
    field_label: str
    field_type: str = "text"
    extraction_hint: str = ""
    review_enforced: bool = False
    review_allowed_values: Optional[List[str]] = None
    sample_value: Optional[str] = None


class ExcelTemplatePlaceholder(BaseModel):
    sheet_name: str
    coordinate: str
    field_key: str
    raw_value: str


class DocumentAnalysis(BaseModel):
    detected_fields: List[DetectedField] = Field(default_factory=list)


class ConfirmTemplateRequest(BaseModel):
    template_name: str
    template_code: str
    description: Optional[str] = None
    fields: List[DetectedField]


class CommitSessionRequest(BaseModel):
    prompt: Optional[str] = None


class SDKModelProfile(BaseModel):
    name: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0, le=2)

    @field_validator("name", "model", "base_url", "api_key", mode="before")
    @classmethod
    def _empty_string_to_none(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def _require_complete_provider_override(self):
        provider_fields = (self.model, self.base_url, self.api_key)
        provided = [value for value in provider_fields if value]
        if provided and len(provided) != len(provider_fields):
            raise ValueError("model、base_url、api_key 必须同时提供或同时省略")
        return self


class SDKModelProfileRequest(BaseModel):
    model_profile: Optional[SDKModelProfile] = None


class CommitResult(BaseModel):
    tenant_id: str
    configuration_id: str
    revision_id: str
    revision_number: int = 1
    field_count: int = 0


class SDKSession(BaseModel):
    id: str
    file_name: str
    file_path: str
    tenant_id: str
    template_name: str
    template_code: str
    instruction: Optional[str] = None
    document_id: str
    parse_job_id: str
    parse_mode: str = "pipeline"
    parse_error: Optional[str] = None
    excel_template_file_name: Optional[str] = None
    excel_template_path: Optional[str] = None
    excel_placeholders: List[ExcelTemplatePlaceholder] = Field(default_factory=list)
    user_id: str
    state: SDKSessionState
    created_at: float
    updated_at: float
    analysis: Optional[DocumentAnalysis] = None
    confirmed_template: Optional[ConfirmTemplateRequest] = None
    prompt: Optional[str] = None
    commit_result: Optional[CommitResult] = None


class SDKSessionResponse(BaseModel):
    id: str
    file_name: str
    tenant_id: str
    template_name: str
    template_code: str
    instruction: Optional[str] = None
    document_id: str
    parse_job_id: str
    parse_mode: str
    parse_error: Optional[str] = None
    parse_progress: Optional[int] = None
    state: SDKSessionState
    excel_template_file_name: Optional[str] = None
    excel_placeholders: List[ExcelTemplatePlaceholder] = Field(default_factory=list)
    analysis: Optional[DocumentAnalysis] = None
    confirmed_template: Optional[ConfirmTemplateRequest] = None
    prompt: Optional[str] = None
    commit_result: Optional[CommitResult] = None


class ParseRetryRequest(BaseModel):
    parse_mode: Optional[str] = None
