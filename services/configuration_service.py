# services/configuration_service.py
"""配置服务 - Project / Configuration / Configuration Revision 领域模型"""

from copy import deepcopy
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from loguru import logger

from services.base import SupabaseClientMixin

CONFIGURATION_TYPES = ("parse", "extract", "classify", "split", "composite")

DEFAULT_PROJECT_NAME = "默认项目"

FIELD_DEFAULTS: Dict[str, Any] = {
    "field_label": "",
    "field_type": "text",
    "extraction_hint": "",
    "feishu_column": "",
    "sort_order": 0,
    "review_enforced": False,
    "review_allowed_values": None,
    "is_required": False,
    "default_value": None,
    "source_doc_type": None,
}

EXAMPLE_DEFAULTS: Dict[str, Any] = {
    "example_output": {},
    "description": None,
    "sort_order": 0,
    "is_active": True,
}

DEFAULT_DEFINITION: Dict[str, Any] = {
    "fields": [],
    "examples": [],
    "extraction_prompt": None,
    "extraction_mode": "ocr_llm",
    "per_page_extraction": False,
    "cleaner_module": None,
    "output_mode": "bitable",
    "push_attachment": True,
    "auto_approve": False,
    "feishu": {"bitable_token": None, "table_id": None},
    "excel": {"file_name": None, "path": None, "placeholders": []},
}


class ConfigurationError(Exception):
    """配置领域异常基类"""


class ConfigurationNotFound(ConfigurationError):
    """配置不存在"""


class ConfigurationStateError(ConfigurationError):
    """配置生命周期状态不允许当前操作"""


def normalize_field(field: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """补齐单个字段的默认键，保留额外键。"""
    field = field or {}
    normalized = dict(FIELD_DEFAULTS)
    normalized.update({k: v for k, v in field.items()})
    return normalized


def normalize_example(example: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """补齐单个示例的默认键，保留额外键。"""
    example = example or {}
    normalized = dict(EXAMPLE_DEFAULTS)
    normalized.update({k: v for k, v in example.items()})
    return normalized


def normalize_definition(definition: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    归一化 Configuration definition：
    - 补齐已知键的默认值
    - fields / examples 逐项归一化
    - feishu / excel 子对象合并而非整体替换
    - 保留未知键（供后续 parse/classify 等类型扩展）
    """
    base = deepcopy(DEFAULT_DEFINITION)
    for key, value in (definition or {}).items():
        if key == "fields":
            base["fields"] = [normalize_field(item) for item in (value or [])]
        elif key == "examples":
            base["examples"] = [normalize_example(item) for item in (value or [])]
        elif key in ("feishu", "excel") and isinstance(value, dict):
            section = dict(base.get(key) or {})
            section.update(value)
            base[key] = section
        else:
            base[key] = value
    return base


def merge_definition(
    base: Optional[Dict[str, Any]],
    patch: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    将补丁合并进已有 definition：
    - fields / examples 为整体替换
    - feishu / excel 为子对象合并
    - 其余键直接覆盖（含显式 None，用于清空可空字段）
    """
    merged = normalize_definition(base)
    for key, value in (patch or {}).items():
        if key in ("feishu", "excel") and isinstance(value, dict):
            section = dict(merged.get(key) or {})
            section.update(value)
            merged[key] = section
        elif key == "fields" and value is not None:
            merged["fields"] = [normalize_field(item) for item in value]
        elif key == "examples" and value is not None:
            merged["examples"] = [normalize_example(item) for item in value]
        else:
            merged[key] = value
    return merged


def build_definition_from_template(
    template: Dict[str, Any],
    fields: Optional[List[Dict[str, Any]]] = None,
    examples: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    将旧 document_templates 记录映射为 Configuration definition。

    与 021_configurations.sql 的 build_legacy_template_definition 保持同构，
    用于数据迁移映射的回归测试及后续兼容读取。
    """
    mapped_fields = []
    for field in sorted(fields or [], key=lambda f: (f.get("sort_order") or 0, f.get("field_key") or "")):
        mapped_fields.append(normalize_field(field))

    mapped_examples = []
    for example in sorted(examples or [], key=lambda e: (e.get("sort_order") or 0, str(e.get("created_at") or ""))):
        mapped_examples.append(normalize_example(example))

    return normalize_definition({
        "fields": mapped_fields,
        "examples": mapped_examples,
        "extraction_prompt": template.get("extraction_prompt_template"),
        "extraction_mode": template.get("extraction_mode") or "ocr_llm",
        "per_page_extraction": bool(template.get("per_page_extraction")),
        "cleaner_module": template.get("cleaner_module"),
        "output_mode": template.get("output_mode") or "bitable",
        "push_attachment": bool(template.get("push_attachment", True)),
        "auto_approve": bool(template.get("auto_approve")),
        "feishu": {
            "bitable_token": template.get("feishu_bitable_token"),
            "table_id": template.get("feishu_table_id"),
        },
        "excel": {
            "file_name": template.get("excel_template_file_name"),
            "path": template.get("excel_template_path"),
            "placeholders": template.get("excel_template_placeholders") or [],
        },
    })


class ConfigurationService(SupabaseClientMixin):
    """配置服务封装"""

    _instance: Optional['ConfigurationService'] = None
    _client = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ============ Project ============

    async def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """按 ID 获取项目"""
        try:
            result = await self._run_sync(
                lambda: self._get_client().table("projects").select("*").eq("id", project_id).execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"获取项目失败: {e}")
            return None

    async def get_default_project(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """获取租户默认项目"""
        try:
            result = await self._run_sync(
                lambda: self._get_client().table("projects").select("*")
                .eq("tenant_id", tenant_id)
                .eq("is_default", True)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"获取默认项目失败: {e}")
            return None

    async def ensure_default_project(self, tenant_id: str) -> Dict[str, Any]:
        """
        获取或创建租户默认项目（最小 Project 实现）。

        并发创建时依赖唯一索引兜底：插入冲突后回读。
        """
        existing = await self.get_default_project(tenant_id)
        if existing:
            return existing

        try:
            result = await self._run_sync(
                lambda: self._get_client().table("projects").insert({
                    "tenant_id": tenant_id,
                    "name": DEFAULT_PROJECT_NAME,
                    "description": "租户默认项目（Configuration 的默认归属）",
                    "is_default": True,
                }).execute()
            )
            if result.data:
                return result.data[0]
        except Exception as e:
            logger.warning(f"创建默认项目失败，尝试回读: {e}")

        existing = await self.get_default_project(tenant_id)
        if existing:
            return existing
        raise ConfigurationError("无法为租户创建默认项目")

    # ============ Configuration ============

    async def list_configurations(
        self,
        tenant_id: Optional[str] = None,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """列出配置（按租户/项目/状态/类型过滤）"""
        try:
            query = self._get_client().table("configurations").select("*")
            if tenant_id:
                query = query.eq("tenant_id", tenant_id)
            if project_id:
                query = query.eq("project_id", project_id)
            if status:
                query = query.eq("status", status)
            if type:
                query = query.eq("type", type)
            query = query.order("created_at", desc=True)
            result = await self._run_sync(query.execute)
            return result.data or []
        except Exception as e:
            logger.error(f"列出配置失败: {e}")
            return []

    async def get_configuration(self, configuration_id: str) -> Optional[Dict[str, Any]]:
        """按 ID 获取配置"""
        try:
            result = await self._run_sync(
                lambda: self._get_client().table("configurations").select("*")
                .eq("id", configuration_id)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"获取配置失败: {e}")
            return None

    async def get_configuration_detail(self, configuration_id: str) -> Optional[Dict[str, Any]]:
        """获取配置详情（含当前已发布 Revision）"""
        configuration = await self.get_configuration(configuration_id)
        if not configuration:
            return None

        detail = dict(configuration)
        revision = None
        if configuration.get("current_revision_id"):
            revision = await self.get_revision(configuration["current_revision_id"])
        detail["current_revision"] = revision
        return detail

    async def create_configuration(
        self,
        data: Dict[str, Any],
        created_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        创建 draft 配置（不产生 Revision，发布时才生成）。

        未指定 project_id 时归属租户默认项目。
        """
        tenant_id = data.get("tenant_id")
        if not tenant_id:
            raise ConfigurationError("缺少 tenant_id")

        project_id = data.get("project_id")
        if project_id:
            project = await self.get_project(project_id)
            if not project or project.get("tenant_id") != tenant_id:
                raise ConfigurationStateError("项目不存在或不属于该租户")
        else:
            project = await self.ensure_default_project(tenant_id)
            project_id = project["id"]

        config_type = data.get("type") or "extract"
        if config_type not in CONFIGURATION_TYPES:
            raise ConfigurationStateError(f"不支持的配置类型: {config_type}")

        payload = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "name": data["name"],
            "code": data.get("code"),
            "description": data.get("description"),
            "type": config_type,
            "status": "draft",
            "draft_definition": normalize_definition(data.get("definition")),
            "created_by": created_by,
        }

        try:
            result = await self._run_sync(
                lambda: self._get_client().table("configurations").insert(payload).execute()
            )
        except Exception as e:
            logger.error(f"创建配置失败: {e}")
            raise

        return result.data[0] if result.data else {}

    async def update_configuration(
        self,
        configuration_id: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        更新 draft 配置；已发布配置的 definition 变更会回到 draft，
        待下次发布生成新 Revision（不修改任何历史 Revision）。
        """
        configuration = await self.get_configuration(configuration_id)
        if not configuration:
            raise ConfigurationNotFound("配置不存在")
        if configuration["status"] == "archived":
            raise ConfigurationStateError("已归档的配置不可修改")

        payload: Dict[str, Any] = {}
        for key in ("name", "code", "description", "type"):
            if data.get(key) is not None:
                payload[key] = data[key]

        if data.get("type") is not None and data["type"] not in CONFIGURATION_TYPES:
            raise ConfigurationStateError(f"不支持的配置类型: {data['type']}")

        if data.get("definition") is not None:
            payload["draft_definition"] = merge_definition(
                configuration.get("draft_definition"),
                data["definition"],
            )
            if configuration["status"] == "published":
                payload["status"] = "draft"

        if not payload:
            return configuration

        try:
            result = await self._run_sync(
                lambda: self._get_client().table("configurations").update(payload)
                .eq("id", configuration_id)
                .execute()
            )
        except Exception as e:
            logger.error(f"更新配置失败: {e}")
            raise

        return result.data[0] if result.data else {**configuration, **payload}

    async def publish_configuration(
        self,
        configuration_id: str,
        created_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        发布 draft 配置：由 draft_definition 生成不可变 Revision 并更新指针。
        """
        configuration = await self.get_configuration(configuration_id)
        if not configuration:
            raise ConfigurationNotFound("配置不存在")
        if configuration["status"] == "archived":
            raise ConfigurationStateError("已归档的配置不可发布")
        if configuration["status"] == "published":
            raise ConfigurationStateError("配置已发布且无待发布的修改")

        definition = normalize_definition(configuration.get("draft_definition"))
        revision_number = await self._next_revision_number(configuration_id)
        published_at = datetime.now(timezone.utc).isoformat()

        try:
            revision_result = await self._run_sync(
                lambda: self._get_client().table("configuration_revisions").insert({
                    "configuration_id": configuration_id,
                    "revision_number": revision_number,
                    "definition": definition,
                    "created_by": created_by,
                    "published_at": published_at,
                }).execute()
            )
            revision = revision_result.data[0] if revision_result.data else {}

            update_result = await self._run_sync(
                lambda: self._get_client().table("configurations").update({
                    "status": "published",
                    "current_revision_id": revision.get("id"),
                }).eq("id", configuration_id).execute()
            )
        except Exception as e:
            logger.error(f"发布配置失败: {e}")
            raise

        updated = update_result.data[0] if update_result.data else {
            **configuration,
            "status": "published",
            "current_revision_id": revision.get("id"),
        }
        return {"configuration": updated, "revision": revision}

    async def archive_configuration(self, configuration_id: str) -> Dict[str, Any]:
        """归档配置（幂等）；归档后不可再修改或发布。"""
        configuration = await self.get_configuration(configuration_id)
        if not configuration:
            raise ConfigurationNotFound("配置不存在")
        if configuration["status"] == "archived":
            return configuration

        try:
            result = await self._run_sync(
                lambda: self._get_client().table("configurations").update({
                    "status": "archived",
                }).eq("id", configuration_id).execute()
            )
        except Exception as e:
            logger.error(f"归档配置失败: {e}")
            raise

        return result.data[0] if result.data else {**configuration, "status": "archived"}

    # ============ Configuration Revision ============

    async def _next_revision_number(self, configuration_id: str) -> int:
        """取下一个 Revision 序号（唯一约束兜底并发）。"""
        try:
            result = await self._run_sync(
                lambda: self._get_client().table("configuration_revisions")
                .select("revision_number")
                .eq("configuration_id", configuration_id)
                .order("revision_number", desc=True)
                .limit(1)
                .execute()
            )
            if result.data:
                return int(result.data[0]["revision_number"]) + 1
        except Exception as e:
            logger.error(f"获取 Revision 序号失败: {e}")
        return 1

    async def list_revisions(self, configuration_id: str) -> List[Dict[str, Any]]:
        """列出配置的所有 Revision（新→旧）"""
        try:
            result = await self._run_sync(
                lambda: self._get_client().table("configuration_revisions").select("*")
                .eq("configuration_id", configuration_id)
                .order("revision_number", desc=True)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"列出 Revision 失败: {e}")
            return []

    async def get_revision(self, revision_id: str) -> Optional[Dict[str, Any]]:
        """按 ID 获取 Revision（只读快照）"""
        try:
            result = await self._run_sync(
                lambda: self._get_client().table("configuration_revisions").select("*")
                .eq("id", revision_id)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"获取 Revision 失败: {e}")
            return None


# 单例实例
configuration_service = ConfigurationService()
