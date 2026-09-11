# tests/services/test_result_service.py
"""ResultService 测试 — JSONB round-trip、逐字段 field_meta、逐样品写入。"""

import pytest

from services.result_service import (
    DEFAULT_SAMPLE_KEY,
    PARSE_SAMPLE_KEY,
    ResultService,
    build_field_meta,
)
from tests.services.test_configuration_service import FakePostgrestClient

TENANT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER_TENANT_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
DOCUMENT_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
JOB_ID = "99999999-9999-4999-8999-999999999999"
REVISION_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"


@pytest.fixture
def service():
    instance = ResultService()
    fake = FakePostgrestClient()
    original_client = instance._client
    instance._client = fake
    yield instance, fake
    instance._client = original_client


class TestFieldMeta:
    def test_build_field_meta_covers_each_field_with_null_confidence(self):
        meta = build_field_meta({"sample_name": "LED灯", "qty": 3}, source="ocr_llm")

        assert set(meta.keys()) == {"sample_name", "qty"}
        assert meta["sample_name"] == {
            "source": "ocr_llm",
            "confidence": None,
            "review_state": "pending",
        }

    def test_build_field_meta_is_empty_for_empty_data(self):
        assert build_field_meta({}) == {}


class TestRoundTrip:
    @pytest.mark.asyncio
    async def test_create_and_get_result_round_trip(self, service):
        svc, _ = service
        data = {"sample_name": "LED灯", "report_date": "2026-01-01"}
        field_meta = build_field_meta(data, source="vlm")

        created = await svc.create_result({
            "tenant_id": TENANT_ID,
            "job_id": JOB_ID,
            "document_id": DOCUMENT_ID,
            "config_revision_id": REVISION_ID,
            "sample_key": "default",
            "data": data,
            "field_meta": field_meta,
            "review_state": "pending",
        })

        fetched = await svc.get_result(created["id"])
        assert fetched["data"] == data
        assert fetched["field_meta"] == field_meta
        assert fetched["review_state"] == "pending"
        assert fetched["tenant_id"] == TENANT_ID
        assert fetched["job_id"] == JOB_ID
        assert fetched["config_revision_id"] == REVISION_ID

    @pytest.mark.asyncio
    async def test_list_filters_by_tenant_job_and_document(self, service):
        svc, _ = service
        await svc.create_result({
            "tenant_id": TENANT_ID, "job_id": JOB_ID, "document_id": DOCUMENT_ID,
            "sample_key": DEFAULT_SAMPLE_KEY, "data": {"a": 1}, "field_meta": {},
        })
        await svc.create_result({
            "tenant_id": OTHER_TENANT_ID, "job_id": "other-job", "document_id": "other-doc",
            "sample_key": DEFAULT_SAMPLE_KEY, "data": {"a": 2}, "field_meta": {},
        })

        own = await svc.list_results(tenant_id=TENANT_ID)
        assert [r["data"] for r in own] == [{"a": 1}]

        by_job = await svc.list_results(job_id=JOB_ID)
        assert len(by_job) == 1

        by_document = await svc.list_results(document_id=DOCUMENT_ID)
        assert len(by_document) == 1

        other = await svc.list_results(tenant_id=OTHER_TENANT_ID)
        assert [r["data"] for r in other] == [{"a": 2}]

    @pytest.mark.asyncio
    async def test_get_missing_result_returns_none(self, service):
        svc, _ = service
        assert await svc.get_result("nope") is None


class TestRecordExtractionResult:
    @pytest.mark.asyncio
    async def test_single_sample_writes_one_result_with_default_key(self, service):
        svc, fake = service
        result = {
            "document_type": "inspection_report",
            "extraction_data": {"sample_name": "LED灯"},
        }

        created = await svc.record_extraction_result(
            tenant_id=TENANT_ID,
            document_id=DOCUMENT_ID,
            result=result,
            job_id=JOB_ID,
            config_revision_id=REVISION_ID,
            source="ocr_llm",
        )

        assert len(created) == 1
        row = fake.tables["results"][0]
        assert row["sample_key"] == DEFAULT_SAMPLE_KEY
        assert row["data"] == {"sample_name": "LED灯"}
        assert row["field_meta"]["sample_name"]["source"] == "ocr_llm"
        assert row["field_meta"]["sample_name"]["confidence"] is None
        assert row["review_state"] == "pending"
        assert row["job_id"] == JOB_ID
        assert row["config_revision_id"] == REVISION_ID
        assert row["document_id"] == DOCUMENT_ID

    @pytest.mark.asyncio
    async def test_per_page_samples_each_get_own_result_row(self, service):
        svc, fake = service
        result = {
            "document_type": "inspection_report",
            "extraction_data": {"sample_name": "第一页"},
            "extraction_results": [
                {"sample_index": 1, "data": {"sample_name": "第一页"}},
                {"sample_index": 2, "data": {"sample_name": "第二页"}},
            ],
        }

        created = await svc.record_extraction_result(
            tenant_id=TENANT_ID,
            document_id=DOCUMENT_ID,
            result=result,
            source="vlm",
        )

        assert len(created) == 2
        rows = fake.tables["results"]
        assert [r["sample_key"] for r in rows] == ["1", "2"]
        assert [r["data"]["sample_name"] for r in rows] == ["第一页", "第二页"]
        assert rows[1]["field_meta"]["sample_name"]["source"] == "vlm"

    @pytest.mark.asyncio
    async def test_missing_tenant_skips_result_write(self, service):
        svc, fake = service
        created = await svc.record_extraction_result(
            tenant_id=None,
            document_id=DOCUMENT_ID,
            result={"extraction_data": {"a": 1}},
        )

        assert created == []
        assert fake.tables.get("results", []) == []


class TestRecordParseResult:
    @pytest.mark.asyncio
    async def test_parse_result_stored_as_single_row_with_parse_sample_key(self, service):
        svc, fake = service
        parse_data = {
            "pages": [{"page_no": 1, "blocks": [], "width": 100, "height": 200}],
            "markdown": "# 标题",
            "engine": {"name": "mineru", "backend": "pipeline"},
            "warnings": [],
        }

        created = await svc.record_parse_result(
            tenant_id=TENANT_ID,
            document_id=DOCUMENT_ID,
            parse_data=parse_data,
            job_id=JOB_ID,
            config_revision_id=REVISION_ID,
        )

        assert created is not None
        row = fake.tables["results"][0]
        assert row["sample_key"] == PARSE_SAMPLE_KEY
        assert row["data"] == parse_data
        assert row["field_meta"] == {}
        assert row["review_state"] == "pending"
        assert row["job_id"] == JOB_ID
        assert row["config_revision_id"] == REVISION_ID

    @pytest.mark.asyncio
    async def test_parse_result_without_tenant_is_skipped(self, service):
        svc, fake = service

        created = await svc.record_parse_result(
            tenant_id=None,
            document_id=DOCUMENT_ID,
            parse_data={"pages": []},
        )

        assert created is None
        assert fake.tables.get("results", []) == []
