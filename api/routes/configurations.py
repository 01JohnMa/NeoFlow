# api/routes/configurations.py
"""配置管理 API - Project / Configuration / Configuration Revision 管理员接口"""

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.configuration_service import (
    configuration_service,
    ConfigurationFieldNotFound,
    ConfigurationNotFound,
    ConfigurationStateError,
)
from api.dependencies.auth import get_current_user, CurrentUser
from api.exceptions import AuthorizationError

router = APIRouter(prefix="/admin/configurations", tags=["配置管理"])

ConfigurationType = Literal["parse", "extract", "classify", "split", "composite"]
ExtractionMode = Literal["ocr_llm", "vlm"]
OutputMode = Literal["bitable", "excel_template", "both"]


# ============ 请求体模型 ============

class ConfigurationFieldModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    field_key: str
    field_label: str
    field_type: Literal["text", "date", "number", "boolean"] = "text"
    extraction_hint: str = ""
    feishu_column: str = ""
    sort_order: int = 0
    review_enforced: bool = False
    review_allowed_values: Optional[List[str]] = None
    is_required: bool = False
    default_value: Optional[str] = None
    source_doc_type: Optional[str] = None


class FeishuOutputModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    bitable_token: Optional[str] = None
    table_id: Optional[str] = None


class ExcelOutputModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    file_name: Optional[str] = None
    path: Optional[str] = None
    placeholders: List[Any] = Field(default_factory=list)


class ConfigurationDefinitionModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    fields: List[ConfigurationFieldModel] = Field(default_factory=list)
    extraction_prompt: Optional[str] = None
    extraction_mode: ExtractionMode = "ocr_llm"
    per_page_extraction: bool = False
    output_mode: OutputMode = "bitable"
    push_attachment: bool = True
    auto_approve: bool = False
    feishu: FeishuOutputModel = Field(default_factory=FeishuOutputModel)
    excel: ExcelOutputModel = Field(default_factory=ExcelOutputModel)


class CreateConfigurationRequest(BaseModel):
    name: str
    tenant_id: Optional[str] = None
    project_id: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    type: ConfigurationType = "extract"
    definition: Optional[ConfigurationDefinitionModel] = None


class UpdateConfigurationRequest(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    type: Optional[ConfigurationType] = None
    definition: Optional[ConfigurationDefinitionModel] = None


class AppendFieldExampleRequest(BaseModel):
    example: str = Field(min_length=1, max_length=500)

    @field_validator("example")
    @classmethod
    def _strip_example(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("示例内容不能为空")
        return stripped


# ============ 权限辅助 ============

def _require_admin(user: CurrentUser) -> None:
    if not user.is_tenant_admin():
        raise AuthorizationError("仅管理员可访问此接口")


def _resolve_tenant_id(request_tenant_id: Optional[str], user: CurrentUser) -> str:
    """租户管理员强制本人租户；超级管理员需要显式或隐含的 tenant_id。"""
    if user.is_super_admin():
        tenant_id = request_tenant_id or user.tenant_id
        if not tenant_id:
            raise HTTPException(status_code=400, detail="super_admin 需指定 tenant_id")
        return tenant_id

    if request_tenant_id and request_tenant_id != user.tenant_id:
        raise AuthorizationError("无权访问其他租户的配置")
    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="当前用户未关联租户")
    return user.tenant_id


async def _require_configuration_access(configuration_id: str, user: CurrentUser) -> Dict[str, Any]:
    configuration = await configuration_service.get_configuration(configuration_id)
    if not configuration:
        raise HTTPException(status_code=404, detail="配置不存在")
    if not user.can_access_tenant(configuration["tenant_id"]):
        raise AuthorizationError("无权访问该配置")
    return configuration


# ============ 配置 CRUD / 生命周期 ============

@router.get("")
async def list_configurations(
    tenant_id: Optional[str] = Query(None, description="按租户过滤（仅 super_admin 有效）"),
    project_id: Optional[str] = Query(None, description="按项目过滤"),
    status: Optional[str] = Query(None, description="draft / published / archived"),
    type: Optional[str] = Query(None, description="parse / extract / classify / split / composite"),
    user: CurrentUser = Depends(get_current_user),
):
    """列出配置：成员不可见其他租户；super_admin 可跨租户查询。"""
    _require_admin(user)

    if user.is_super_admin():
        effective_tenant_id = tenant_id
    else:
        effective_tenant_id = user.tenant_id

    return await configuration_service.list_configurations(
        tenant_id=effective_tenant_id,
        project_id=project_id,
        status=status,
        type=type,
    )


@router.post("", status_code=201)
async def create_configuration(
    request: CreateConfigurationRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """创建 draft 配置（未指定项目时归入租户默认项目，发布前不产生 Revision）。"""
    _require_admin(user)

    tenant_id = _resolve_tenant_id(request.tenant_id, user)
    payload = request.model_dump(exclude_unset=True)
    payload["tenant_id"] = tenant_id

    configuration = await configuration_service.create_configuration(
        payload,
        created_by=user.user_id,
    )
    return {"success": True, "data": configuration}


@router.get("/{configuration_id}")
async def get_configuration(
    configuration_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """获取配置详情（含当前已发布 Revision）。"""
    _require_admin(user)
    await _require_configuration_access(configuration_id, user)
    return await configuration_service.get_configuration_detail(configuration_id)


@router.put("/{configuration_id}")
async def update_configuration(
    configuration_id: str,
    request: UpdateConfigurationRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """
    更新 draft 配置。

    已发布配置的 definition 一旦变更即回到 draft，下次发布会生成新 Revision；
    历史 Revision 永不被修改。
    """
    _require_admin(user)
    await _require_configuration_access(configuration_id, user)

    data = request.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="无有效更新字段")

    try:
        updated = await configuration_service.update_configuration(configuration_id, data)
    except ConfigurationNotFound:
        raise HTTPException(status_code=404, detail="配置不存在")
    except ConfigurationStateError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"success": True, "data": updated}


@router.post("/{configuration_id}/publish")
async def publish_configuration(
    configuration_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """发布配置：由 draft 定义生成不可变 Revision 并指向它。"""
    _require_admin(user)
    await _require_configuration_access(configuration_id, user)

    try:
        result = await configuration_service.publish_configuration(
            configuration_id,
            created_by=user.user_id,
        )
    except ConfigurationNotFound:
        raise HTTPException(status_code=404, detail="配置不存在")
    except ConfigurationStateError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"success": True, "data": result}


@router.post("/{configuration_id}/archive")
async def archive_configuration(
    configuration_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """归档配置；归档后不可修改或发布（幂等）。"""
    _require_admin(user)
    await _require_configuration_access(configuration_id, user)

    try:
        configuration = await configuration_service.archive_configuration(configuration_id)
    except ConfigurationNotFound:
        raise HTTPException(status_code=404, detail="配置不存在")

    return {"success": True, "data": configuration}


# ============ 字段示例（从已审核结果写回 few-shot） ============

@router.post("/{configuration_id}/fields/{field_key}/examples")
async def append_field_example(
    configuration_id: str,
    field_key: str,
    request: AppendFieldExampleRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """
    把经验证的片段追加到字段描述，并以新 Revision 保存。

    已发布 Revision 不被就地修改：定义先落入 draft，随即发布生成新 Revision。
    """
    _require_admin(user)
    await _require_configuration_access(configuration_id, user)

    try:
        result = await configuration_service.append_field_example(
            configuration_id,
            field_key,
            request.example,
            created_by=user.user_id,
        )
    except ConfigurationNotFound:
        raise HTTPException(status_code=404, detail="配置不存在")
    except ConfigurationFieldNotFound:
        raise HTTPException(status_code=404, detail="字段不存在")
    except ConfigurationStateError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"success": True, "data": result}


# ============ Revision（只读） ============

@router.get("/{configuration_id}/revisions")
async def list_revisions(
    configuration_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """列出配置的发布修订历史（新→旧）。"""
    _require_admin(user)
    await _require_configuration_access(configuration_id, user)
    return await configuration_service.list_revisions(configuration_id)


@router.get("/{configuration_id}/revisions/{revision_id}")
async def get_revision(
    configuration_id: str,
    revision_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """读取单个不可变 Revision。"""
    _require_admin(user)
    await _require_configuration_access(configuration_id, user)

    revision = await configuration_service.get_revision(revision_id)
    if not revision or revision.get("configuration_id") != configuration_id:
        raise HTTPException(status_code=404, detail="修订不存在")

    return revision
