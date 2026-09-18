# tests/services/test_result_service.py
"""ResultService 测试 — JSONB round-trip、按租户/Job/文档过滤、Parse 单行写入。"""

import pytest

from services.result_service import (
    DEFAULT_SAMPLE_KEY,
    PARSE_SAMPLE_KEY,
    ResultService,
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


class TestRoundTrip:
    @pytest.mark.asyncio
    async def test_create_and_get_result_round_trip(self, service):
        svc, _ = service
        data = {"sample_name": "LED灯", "report_date": "2026-01-01"}

        created = await svc.create_result({
            "tenant_id": TENANT_ID,
            "job_id": JOB_ID,
            "document_id": DOCUMENT_ID,
            "config_revision_id": REVISION_ID,
            "sample_key": "default",
            "data": data,
        })

        fetched = await svc.list_results(job_id=JOB_ID)
        assert fetched[0]["data"] == data
        assert fetched[0]["tenant_id"] == TENANT_ID
        assert fetched[0]["job_id"] == JOB_ID
        assert fetched[0]["config_revision_id"] == REVISION_ID
        assert fetched[0]["id"] == created["id"]

    @pytest.mark.asyncio
    async def test_list_filters_by_tenant_job_and_document(self, service):
        svc, _ = service
        await svc.create_result({
            "tenant_id": TENANT_ID, "job_id": JOB_ID, "document_id": DOCUMENT_ID,
            "sample_key": DEFAULT_SAMPLE_KEY, "data": {"a": 1},
        })
        await svc.create_result({
            "tenant_id": OTHER_TENANT_ID, "job_id": "other-job", "document_id": "other-doc",
            "sample_key": DEFAULT_SAMPLE_KEY, "data": {"a": 2},
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
    async def test_list_results_excludes_sample_key(self, service):
        svc, _ = service
        await svc.create_result({
            "tenant_id": TENANT_ID, "document_id": DOCUMENT_ID,
            "sample_key": DEFAULT_SAMPLE_KEY, "data": {"a": 1},
        })
        await svc.create_result({
            "tenant_id": TENANT_ID, "document_id": DOCUMENT_ID,
            "sample_key": PARSE_SAMPLE_KEY, "data": {"markdown": "x"},
        })

        rows = await svc.list_results(
            tenant_id=TENANT_ID,
            document_id=DOCUMENT_ID,
            exclude_sample_key=PARSE_SAMPLE_KEY,
        )
        assert [r["data"] for r in rows] == [{"a": 1}]


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

    @pytest.mark.asyncio
    async def test_get_document_parse_result_returns_latest_parse_row(self, service):
        svc, _ = service
        await svc.create_result({
            "tenant_id": TENANT_ID, "document_id": DOCUMENT_ID,
            "sample_key": DEFAULT_SAMPLE_KEY, "data": {"a": 1},
        })
        created = await svc.record_parse_result(
            tenant_id=TENANT_ID,
            document_id=DOCUMENT_ID,
            parse_data={"markdown": "old"},
        )

        found = await svc.get_document_parse_result(DOCUMENT_ID, tenant_id=TENANT_ID)

        assert found is not None
        assert found["id"] == created["id"]


class TestFilterBeforeLimit:
    """sample_key 过滤必须发生在 LIMIT 之前，避免被截断窗口挤出。"""

    @pytest.mark.asyncio
    async def test_parse_result_survives_many_newer_extraction_rows(self, service):
        svc, _ = service
        parse_row = await svc.create_result(svc.build_result_row(
            tenant_id=TENANT_ID,
            document_id=DOCUMENT_ID,
            data={"markdown": "old-parse"},
            sample_key=PARSE_SAMPLE_KEY,
        ))
        for index in range(55):
            await svc.create_result(svc.build_result_row(
                tenant_id=TENANT_ID,
                document_id=DOCUMENT_ID,
                data={"sample_name": f"n{index}"},
                sample_key=DEFAULT_SAMPLE_KEY,
            ))

        found = await svc.get_document_parse_result(DOCUMENT_ID, tenant_id=TENANT_ID)

        assert found is not None
        assert found["id"] == parse_row["id"]

    @pytest.mark.asyncio
    async def test_extraction_result_survives_many_parse_reruns(self, service):
        svc, _ = service
        extraction_row = await svc.create_result(svc.build_result_row(
            tenant_id=TENANT_ID,
            document_id=DOCUMENT_ID,
            data={"sample_name": "kept"},
            sample_key=DEFAULT_SAMPLE_KEY,
        ))
        for index in range(205):
            await svc.create_result(svc.build_result_row(
                tenant_id=TENANT_ID,
                document_id=DOCUMENT_ID,
                data={"markdown": f"parse-{index}"},
                sample_key=PARSE_SAMPLE_KEY,
            ))

        found_rows = await svc.list_results(
            tenant_id=TENANT_ID,
            document_id=DOCUMENT_ID,
            exclude_sample_key=PARSE_SAMPLE_KEY,
            limit=1,
        )

        assert found_rows[0]["id"] == extraction_row["id"]


class TestReadFailureAndOrdering:
    @pytest.mark.asyncio
    async def test_list_results_propagates_db_errors(self, service, monkeypatch):
        svc, _ = service

        class BrokenQuery:
            def select(self, *args, **kwargs):
                raise RuntimeError("db down")

        class BrokenClient:
            def table(self, name):
                return BrokenQuery()

        monkeypatch.setattr(svc, "_get_client", lambda: BrokenClient())

        with pytest.raises(RuntimeError):
            await svc.list_results(document_id=DOCUMENT_ID)

    @pytest.mark.asyncio
    async def test_latest_tie_broken_by_id_desc(self, service):
        svc, fake = service
        await svc.create_result({
            "tenant_id": TENANT_ID, "document_id": DOCUMENT_ID,
            "sample_key": "extract", "data": {"a": 1},
        })
        await svc.create_result({
            "tenant_id": TENANT_ID, "document_id": DOCUMENT_ID,
            "sample_key": "extract", "data": {"a": 2},
        })
        rows = fake.tables["results"]
        rows[0]["created_at"] = rows[1]["created_at"] = "2026-01-01T00:00:00+00:00"
        rows[0]["id"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        rows[1]["id"] = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"

        fetched = await svc.list_results(document_id=DOCUMENT_ID, limit=1)

        assert fetched[0]["data"] == {"a": 2}
