# tests/services/test_configuration_service.py
"""ConfigurationService 生命周期测试 — 使用内存版 PostgREST fake，不依赖数据库。"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

from services.base import build_extraction_prompt
from services.configuration_service import (
    ConfigurationFieldNotFound,
    ConfigurationNotFound,
    ConfigurationService,
    ConfigurationStateError,
    build_extraction_config,
    merge_definition,
    normalize_definition,
)

TENANT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER_TENANT_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
USER_ID = "11111111-1111-4111-8111-111111111111"


class FakeResult:
    def __init__(self, data: List[Dict[str, Any]], count: Optional[int] = None):
        self.data = data
        self.count = count


class FakeQuery:
    def __init__(self, store: Dict[str, List[Dict[str, Any]]], table_name: str):
        self.store = store
        self.table_name = table_name
        self._operation = "select"
        self._payload: Optional[Dict[str, Any]] = None
        self._filters = []
        self._order_key: Optional[str] = None
        self._order_desc = False
        self._limit: Optional[int] = None

    def select(self, columns: str = "*", count: Optional[str] = None):
        self._operation = "select"
        return self

    def insert(self, payload: Dict[str, Any]):
        self._operation = "insert"
        self._payload = dict(payload)
        return self

    def update(self, payload: Dict[str, Any]):
        self._operation = "update"
        self._payload = dict(payload)
        return self

    def delete(self):
        self._operation = "delete"
        return self

    def eq(self, key: str, value: Any):
        self._filters.append(("eq", key, value))
        return self

    def in_(self, key: str, values: List[Any]):
        self._filters.append(("in", key, list(values)))
        return self

    def order(self, key: str, desc: bool = False):
        self._order_key = key
        self._order_desc = desc
        return self

    def limit(self, count: int):
        self._limit = count
        return self

    def _matches(self, row: Dict[str, Any]) -> bool:
        for op, key, value in self._filters:
            if op == "eq" and row.get(key) != value:
                return False
            if op == "in" and row.get(key) not in value:
                return False
        return True

    def execute(self) -> FakeResult:
        table = self.store.setdefault(self.table_name, [])

        if self._operation == "insert":
            row = dict(self._payload or {})
            row.setdefault("id", str(uuid.uuid4()))
            now = datetime.now(timezone.utc).isoformat()
            row.setdefault("created_at", now)
            if self.table_name != "configuration_revisions":
                row.setdefault("updated_at", now)
            if self.table_name == "configurations":
                row.setdefault("current_revision_id", None)
                row.setdefault("status", "draft")
                row.setdefault("draft_definition", {})
                row.setdefault("code", None)
                row.setdefault("description", None)
            if self.table_name == "projects":
                row.setdefault("is_default", False)
                row.setdefault("description", None)
            table.append(row)
            return FakeResult([dict(row)])

        if self._operation == "update":
            if self.table_name == "configuration_revisions":
                raise RuntimeError("immutable: configuration_revisions 不可 UPDATE")
            updated = []
            for row in table:
                if self._matches(row):
                    row.update(self._payload or {})
                    updated.append(dict(row))
            return FakeResult(updated)

        if self._operation == "delete":
            removed = [row for row in table if self._matches(row)]
            self.store[self.table_name] = [row for row in table if not self._matches(row)]
            return FakeResult(removed)

        rows = [dict(row) for row in table if self._matches(row)]
        if self._order_key:
            rows.sort(key=lambda r: r.get(self._order_key), reverse=self._order_desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        return FakeResult(rows, count=len(rows))


class FakePostgrestClient:
    def __init__(self):
        self.tables: Dict[str, List[Dict[str, Any]]] = {}

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self.tables, name)


@pytest.fixture
def service():
    instance = ConfigurationService()
    fake = FakePostgrestClient()
    original_client = instance._client
    instance._client = fake
    yield instance, fake
    instance._client = original_client


def _create(name="测试配置", tenant_id=TENANT_ID, **overrides):
    payload = {
        "tenant_id": tenant_id,
        "name": name,
        "type": "extract",
        "definition": overrides.pop("definition", None),
    }
    payload.update(overrides)
    return payload


class TestCreateConfiguration:
    @pytest.mark.asyncio
    async def test_create_draft_has_no_revision(self, service):
        svc, fake = service
        created = await svc.create_configuration(_create())

        assert created["status"] == "draft"
        assert created["current_revision_id"] is None
        assert created["draft_definition"]["extraction_mode"] == "ocr_llm"
        assert fake.tables.get("configuration_revisions", []) == []

    @pytest.mark.asyncio
    async def test_create_uses_default_project_and_reuses_it(self, service):
        svc, fake = service
        first = await svc.create_configuration(_create(name="A"))
        second = await svc.create_configuration(_create(name="B"))

        projects = fake.tables["projects"]
        assert len(projects) == 1
        assert projects[0]["is_default"] is True
        assert first["project_id"] == second["project_id"] == projects[0]["id"]

    @pytest.mark.asyncio
    async def test_create_with_project_from_other_tenant_rejected(self, service):
        svc, fake = service
        fake.tables["projects"] = [{
            "id": "p-other",
            "tenant_id": OTHER_TENANT_ID,
            "name": "别的项目",
            "is_default": True,
        }]
        with pytest.raises(ConfigurationStateError):
            await svc.create_configuration(_create(project_id="p-other"))

    @pytest.mark.asyncio
    async def test_create_normalizes_definition_fields(self, service):
        svc, _ = service
        created = await svc.create_configuration(_create(
            svc,
            definition={
                "fields": [{"field_key": "sample_name", "field_label": "样品名称"}],
                "extraction_prompt": "抽取字段",
                "extraction_mode": "vlm",
                "per_page_extraction": True,
            },
        ))

        definition = created["draft_definition"]
        assert definition["extraction_prompt"] == "抽取字段"
        assert definition["extraction_mode"] == "vlm"
        assert definition["per_page_extraction"] is True
        assert definition["fields"][0]["field_type"] == "text"
        assert definition["fields"][0]["sort_order"] == 0

    @pytest.mark.asyncio
    async def test_parse_configuration_merges_parse_defaults_and_publishes(self, service):
        svc, _ = service
        created = await svc.create_configuration(_create(
            type="parse",
            definition={"parse": {"model_version": "vlm", "method": "ocr"}},
        ))

        parse_section = created["draft_definition"]["parse"]
        assert parse_section["model_version"] == "vlm"
        assert parse_section["method"] == "ocr"
        assert parse_section["backend"] == "mineru-api"
        assert parse_section["effort"] == "medium"

        published = await svc.publish_configuration(created["id"], created_by=USER_ID)
        assert published["revision"]["definition"]["parse"]["model_version"] == "vlm"


class TestPublishLifecycle:
    @pytest.mark.asyncio
    async def test_publish_creates_immutable_revision_and_pointer(self, service):
        svc, fake = service
        created = await svc.create_configuration(_create(definition={"extraction_prompt": "v1"}))

        result = await svc.publish_configuration(created["id"], created_by=USER_ID)

        configuration = result["configuration"]
        revision = result["revision"]
        assert configuration["status"] == "published"
        assert configuration["current_revision_id"] == revision["id"]
        assert revision["revision_number"] == 1
        assert revision["definition"]["extraction_prompt"] == "v1"
        assert revision["published_at"] is not None
        assert len(fake.tables["configuration_revisions"]) == 1

    @pytest.mark.asyncio
    async def test_publish_published_without_changes_rejected(self, service):
        svc, _ = service
        created = await svc.create_configuration(_create())
        await svc.publish_configuration(created["id"])

        with pytest.raises(ConfigurationStateError):
            await svc.publish_configuration(created["id"])

    @pytest.mark.asyncio
    async def test_publish_unimplemented_type_rejected(self, service):
        svc, _ = service
        created = await svc.create_configuration(_create(type="classify"))

        with pytest.raises(ConfigurationStateError, match="尚未实现"):
            await svc.publish_configuration(created["id"])

    @pytest.mark.asyncio
    async def test_update_published_creates_new_draft_then_new_revision(self, service):
        svc, _ = service
        created = await svc.create_configuration(_create(definition={"extraction_prompt": "v1"}))
        first = await svc.publish_configuration(created["id"])
        first_revision = first["revision"]

        updated = await svc.update_configuration(created["id"], {
            "definition": {"extraction_prompt": "v2"},
        })
        assert updated["status"] == "draft"
        assert updated["current_revision_id"] == first_revision["id"]
        assert updated["draft_definition"]["extraction_prompt"] == "v2"
        assert len(await svc.list_revisions(created["id"])) == 1

        second = await svc.publish_configuration(created["id"])
        assert second["revision"]["revision_number"] == 2
        assert second["revision"]["definition"]["extraction_prompt"] == "v2"

        revisions = await svc.list_revisions(created["id"])
        assert [r["revision_number"] for r in revisions] == [2, 1]
        old = await svc.get_revision(first_revision["id"])
        assert old["definition"]["extraction_prompt"] == "v1"

    @pytest.mark.asyncio
    async def test_update_draft_does_not_create_revision(self, service):
        svc, _ = service
        created = await svc.create_configuration(_create())
        updated = await svc.update_configuration(created["id"], {
            "name": "改名",
            "definition": {"per_page_extraction": True},
        })

        assert updated["status"] == "draft"
        assert updated["name"] == "改名"
        assert updated["draft_definition"]["per_page_extraction"] is True
        assert await svc.list_revisions(created["id"]) == []

    @pytest.mark.asyncio
    async def test_definition_merge_keeps_untouched_sections(self, service):
        svc, _ = service
        created = await svc.create_configuration(_create(
            svc,
            definition={
                "fields": [{"field_key": "a", "field_label": "A", "sort_order": 1}],
                "feishu": {"bitable_token": "token-1", "table_id": "table-1"},
            },
        ))
        updated = await svc.update_configuration(created["id"], {
            "definition": {"feishu": {"table_id": "table-2"}, "auto_approve": True},
        })

        definition = updated["draft_definition"]
        assert definition["fields"][0]["field_key"] == "a"
        assert definition["feishu"] == {"bitable_token": "token-1", "table_id": "table-2"}
        assert definition["auto_approve"] is True


class TestFieldExamples:
    async def _published(self, svc, hint="位于样品名称标签后"):
        created = await svc.create_configuration(_create(definition={
            "fields": [{
                "field_key": "sample_name",
                "field_label": "样品名称",
                "extraction_hint": hint,
            }],
            "extraction_prompt": None,
        }))
        return await svc.publish_configuration(created["id"], created_by=USER_ID)

    @pytest.mark.asyncio
    async def test_append_example_creates_new_revision_keeping_old(self, service):
        svc, _ = service
        published = await self._published(svc)
        configuration_id = published["configuration"]["id"]

        result = await svc.append_field_example(
            configuration_id, "sample_name", "LED 灯", created_by=USER_ID,
        )

        revision = result["revision"]
        assert revision["revision_number"] == 2
        assert result["configuration"]["status"] == "published"
        assert result["configuration"]["current_revision_id"] == revision["id"]
        assert "示例：LED 灯" in revision["definition"]["fields"][0]["extraction_hint"]

        old = await svc.get_revision(published["revision"]["id"])
        assert "示例" not in old["definition"]["fields"][0]["extraction_hint"]

    @pytest.mark.asyncio
    async def test_updated_hint_reaches_extraction_prompt(self, service):
        svc, _ = service
        published = await self._published(svc)
        configuration_id = published["configuration"]["id"]

        appended = await svc.append_field_example(configuration_id, "sample_name", "LED 灯")

        config = await svc.get_extraction_configuration(configuration_id)
        assert config["revision_id"] == appended["revision"]["id"]
        assert "示例：LED 灯" in config["fields"][0]["extraction_hint"]

        prompt = build_extraction_prompt(config, "样品名称：LED 灯")
        assert "示例：LED 灯" in prompt

    @pytest.mark.asyncio
    async def test_append_same_example_is_idempotent(self, service):
        svc, _ = service
        published = await self._published(svc)
        configuration_id = published["configuration"]["id"]

        first = await svc.append_field_example(configuration_id, "sample_name", "LED 灯")
        second = await svc.append_field_example(configuration_id, "sample_name", "  LED 灯  ")

        assert second["revision"]["id"] == first["revision"]["id"]
        assert len(await svc.list_revisions(configuration_id)) == 2

    @pytest.mark.asyncio
    async def test_append_example_missing_field_rejected(self, service):
        svc, _ = service
        published = await self._published(svc)
        with pytest.raises(ConfigurationFieldNotFound):
            await svc.append_field_example(
                published["configuration"]["id"], "unknown_field", "x",
            )

    @pytest.mark.asyncio
    async def test_append_example_archived_rejected(self, service):
        svc, _ = service
        published = await self._published(svc)
        configuration_id = published["configuration"]["id"]
        await svc.archive_configuration(configuration_id)

        with pytest.raises(ConfigurationStateError):
            await svc.append_field_example(configuration_id, "sample_name", "LED 灯")

    @pytest.mark.asyncio
    async def test_append_example_unknown_configuration(self, service):
        svc, _ = service
        with pytest.raises(ConfigurationNotFound):
            await svc.append_field_example("missing-config", "sample_name", "LED 灯")


class TestArchive:
    @pytest.mark.asyncio
    async def test_archive_published_blocks_update_and_publish(self, service):
        svc, _ = service
        created = await svc.create_configuration(_create())
        await svc.publish_configuration(created["id"])

        archived = await svc.archive_configuration(created["id"])
        assert archived["status"] == "archived"

        with pytest.raises(ConfigurationStateError):
            await svc.update_configuration(created["id"], {"name": "x"})
        with pytest.raises(ConfigurationStateError):
            await svc.publish_configuration(created["id"])

        again = await svc.archive_configuration(created["id"])
        assert again["status"] == "archived"

    @pytest.mark.asyncio
    async def test_archived_revision_still_readable(self, service):
        svc, _ = service
        created = await svc.create_configuration(_create(definition={"extraction_prompt": "keep"}))
        published = await svc.publish_configuration(created["id"])
        await svc.archive_configuration(created["id"])

        revision = await svc.get_revision(published["revision"]["id"])
        assert revision["definition"]["extraction_prompt"] == "keep"


class TestTenantScoping:
    @pytest.mark.asyncio
    async def test_list_filters_by_tenant(self, service):
        svc, _ = service
        await svc.create_configuration(_create(name="本租户", tenant_id=TENANT_ID))
        await svc.create_configuration(_create(name="别租户", tenant_id=OTHER_TENANT_ID))

        rows = await svc.list_configurations(tenant_id=TENANT_ID)
        assert [r["name"] for r in rows] == ["本租户"]

    @pytest.mark.asyncio
    async def test_list_filters_by_status_and_type(self, service):
        svc, _ = service
        draft = await svc.create_configuration(_create(name="draft"))
        published = await svc.create_configuration(_create(name="published"))
        await svc.publish_configuration(published["id"])

        drafts = await svc.list_configurations(tenant_id=TENANT_ID, status="draft")
        assert [r["id"] for r in drafts] == [draft["id"]]

        extracts = await svc.list_configurations(tenant_id=TENANT_ID, type="extract")
        assert len(extracts) == 2


class TestDefinitionHelpers:
    def test_merge_definition_replaces_field_list(self):
        merged = merge_definition(
            {"fields": [{"field_key": "a", "field_label": "A"}], "extraction_mode": "vlm"},
            {"fields": [{"field_key": "b", "field_label": "B"}]},
        )
        assert [f["field_key"] for f in merged["fields"]] == ["b"]
        assert merged["extraction_mode"] == "vlm"

    def test_normalize_definition_preserves_unknown_keys(self):
        definition = normalize_definition({"custom_param": {"level": 2}})
        assert definition["custom_param"] == {"level": 2}
        assert "examples" not in definition

    def test_normalize_definition_drops_legacy_examples(self):
        definition = normalize_definition(
            {"examples": [{"example_input": "输入", "example_output": {"a": 1}}]}
        )
        assert "examples" not in definition

    def test_normalize_definition_drops_legacy_cleaner_module(self):
        definition = normalize_definition({"cleaner_module": "legacy.cleaner"})
        assert "cleaner_module" not in definition

    def test_merge_definition_ignores_legacy_dead_keys(self):
        merged = merge_definition(
            {},
            {
                "cleaner_module": "legacy.cleaner",
                "examples": [{"example_input": "输入", "example_output": {"a": 1}}],
            },
        )
        assert "cleaner_module" not in merged
        assert "examples" not in merged


class TestExtractionConfig:
    def test_build_extraction_config_maps_definition_and_defaults(self):
        configuration = {
            "id": "c-1",
            "tenant_id": TENANT_ID,
            "name": "检测报告",
            "code": "inspection_report",
            "type": "extract",
            "status": "published",
            "current_revision_id": "r-1",
            "draft_definition": {
                "fields": [{"field_key": "a", "field_label": "A"}],
                "examples": [{"example_input": "输入", "example_output": {"a": 1}}],
                "extraction_prompt": "请抽取字段",
                "extraction_mode": "vlm",
                "per_page_extraction": True,
                "output_mode": "both",
                "push_attachment": False,
                "auto_approve": True,
                "feishu": {"bitable_token": "app-token", "table_id": "tbl-1"},
                "excel": {
                    "file_name": "模板.xlsx",
                    "path": "/uploads/template.xlsx",
                    "placeholders": [{"field_key": "a"}],
                },
            },
        }

        config = build_extraction_config(configuration)

        assert config["id"] == "c-1"
        assert config["revision_id"] == "r-1"
        assert config["fields"][0]["field_key"] == "a"
        assert config["fields"][0]["field_type"] == "text"
        assert "examples" not in config
        assert config["extraction_prompt"] == "请抽取字段"
        assert config["extraction_mode"] == "vlm"
        assert config["per_page_extraction"] is True
        assert config["push_attachment"] is False
        assert config["auto_approve"] is True
        assert config["feishu"] == {"bitable_token": "app-token", "table_id": "tbl-1"}
        assert config["excel"]["path"] == "/uploads/template.xlsx"
        assert "cleaner_module" not in config

    def test_build_extraction_config_empty_uses_defaults(self):
        config = build_extraction_config({"id": "c-1", "draft_definition": {}})
        assert config["fields"] == []
        assert "examples" not in config
        assert config["extraction_mode"] == "ocr_llm"
        assert config["output_mode"] == "bitable"
        assert "cleaner_module" not in config
        assert config["push_attachment"] is True

    @pytest.mark.asyncio
    async def test_get_extraction_configuration_prefers_published_revision(self, service):
        svc, _ = service
        created = await svc.create_configuration(_create(definition={"extraction_prompt": "v1"}))
        published = await svc.publish_configuration(created["id"])
        await svc.update_configuration(created["id"], {"definition": {"extraction_prompt": "draft-v2"}})

        config = await svc.get_extraction_configuration(created["id"])
        assert config["extraction_prompt"] == "v1"
        assert config["revision_id"] == published["revision"]["id"]

    @pytest.mark.asyncio
    async def test_get_extraction_configuration_by_revision_pins_definition(self, service):
        svc, _ = service
        created = await svc.create_configuration(_create(definition={"extraction_prompt": "v1"}))
        published = await svc.publish_configuration(created["id"])
        await svc.update_configuration(created["id"], {"definition": {"extraction_prompt": "v2"}})
        second = await svc.publish_configuration(created["id"])

        old = await svc.get_extraction_configuration_by_revision(published["revision"]["id"])
        new = await svc.get_extraction_configuration_by_revision(second["revision"]["id"])
        assert old["extraction_prompt"] == "v1"
        assert new["extraction_prompt"] == "v2"
        assert old["revision_id"] == published["revision"]["id"]

    @pytest.mark.asyncio
    async def test_resolve_extraction_configuration_by_config_id_code_and_name(self, service):
        svc, _ = service
        created = await svc.create_configuration(
            _create(name="检测报告", code="inspection_report")
        )
        await svc.publish_configuration(created["id"])

        by_id = await svc.resolve_extraction_configuration(TENANT_ID, created["id"])
        by_code = await svc.resolve_extraction_configuration(TENANT_ID, "inspection_report")
        by_name = await svc.resolve_extraction_configuration(TENANT_ID, "检测报告")

        assert by_id["id"] == created["id"]
        assert by_code["id"] == created["id"]
        assert by_name["id"] == created["id"]
        assert await svc.resolve_extraction_configuration(OTHER_TENANT_ID, created["id"]) is None

    @pytest.mark.asyncio
    async def test_resolve_by_legacy_template_id_and_list_published(self, service):
        svc, fake = service
        legacy_id = "b0000000-0000-0000-0000-000000000001"
        created = await svc.create_configuration(_create(name="检测报告", code="inspection_report"))
        await svc.publish_configuration(created["id"])
        fake.tables["configurations"][0]["legacy_template_id"] = legacy_id

        draft = await svc.create_configuration(_create(name="草稿配置", code="draft_only"))

        resolved = await svc.resolve_extraction_configuration(TENANT_ID, legacy_id)
        assert resolved["id"] == created["id"]

        published_configs = await svc.list_published_extract_configurations(TENANT_ID)
        ids = [c["id"] for c in published_configs]
        assert created["id"] in ids
        assert draft["id"] not in ids
