# tests/services/test_extract_service.py
"""Extract handler 测试：绑定、预算、修复环、状态机、交卷确认与失败路径（假 LLM/RPC）。"""

import asyncio
import httpx
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from services import extract_service
from services.extract_service import (
    ExtractFailure,
    build_execution_spec,
    build_engine,
    handle_extract_job,
    plan_units,
    resolve_extract_spec,
    validate_output,
)
from services.llm_invoke import LLMResult
from services.page_index import PageCandidate, PageIndexPage, PageIndexSnapshot, PageIndexService, InMemoryPageEmbeddingStore

JOB_ID = "99999999-9999-4999-8999-999999999999"
DOCUMENT_ID = "11111111-1111-4111-8111-111111111111"
TENANT_ID = "a0000000-0000-0000-0000-000000000001"
RESULT_ID = "22222222-2222-4222-8222-222222222222"


def _deadline_iso(seconds: float = 600) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()

SCHEMA = {
    "type": "object",
    "properties": {
        "report_no": {"type": "string"},
        "conclusion": {"type": ["string", "null"]},
    },
    "required": ["report_no"],
    "additionalProperties": False,
}


def _job(**overrides):
    job = {
        "job_id": JOB_ID,
        "locked_by": "worker-1",
        "attempts": 1,
        "status": "processing",
        "tenant_id": TENANT_ID,
        "document_ids": [DOCUMENT_ID],
        "configuration_revision_id": None,
        "execution_spec": {
            "capability": "extract",
            "spec_version": "1",
            "effective_params": {"target": "per_doc", "data_schema": SCHEMA},
        },
    }
    job.update(overrides)
    return job


def _document():
    return {
        "id": DOCUMENT_ID,
        "tenant_id": TENANT_ID,
        "file_path": "/tmp/demo.pdf",
    }


def _parse_data(pages: int = 1):
    return {
        "markdown": " ".join(f"page {index + 1}" for index in range(pages)),
        "pages": [
            {"page_no": index + 1, "markdown": f"page {index + 1}", "blocks": []}
            for index in range(pages)
        ],
    }


def _parse_row(data=None):
    return {
        "id": RESULT_ID,
        "document_id": DOCUMENT_ID,
        "tenant_id": TENANT_ID,
        "sample_key": "parse",
        "data": data if data is not None else _parse_data(),
    }


def _llm_result(
    content: str,
    finish_reason="stop",
    refusal=None,
    content_invalid=False,
):
    return LLMResult(
        content=content,
        finish_reason=finish_reason,
        model="fake-model",
        input_tokens=10,
        output_tokens=5,
        request_id="req-1",
        refusal=refusal,
        content_invalid=content_invalid,
    )


def _patch_env(
    monkeypatch,
    *,
    parse_row=None,
    llm_responses=None,
    bind_status="bound",
    budget=None,
    renewed=True,
    auto_parse=True,
    commit_status="completed",
):
    monkeypatch.setattr(
        extract_service.supabase_service, "get_document", AsyncMock(return_value=_document())
    )
    monkeypatch.setattr(
        extract_service.result_service, "get_document_parse_result",
        AsyncMock(return_value=parse_row if parse_row is not None else _parse_row()),
    )
    monkeypatch.setattr(
        extract_service.result_service, "get_result",
        AsyncMock(return_value=parse_row if parse_row is not None else _parse_row()),
    )
    monkeypatch.setattr(
        extract_service, "ensure_parse_result",
        AsyncMock(return_value=_parse_data() if auto_parse else None),
    )
    monkeypatch.setattr(
        extract_service, "bind_extract_parse_result", AsyncMock(return_value=bind_status)
    )
    monkeypatch.setattr(
        extract_service, "ensure_extract_budget",
        AsyncMock(
            return_value=budget
            or {"status": "initialized", "requests_used": 0, "max_requests": 200,
                "deadline": _deadline_iso()}
        ),
    )
    monkeypatch.setattr(
        extract_service, "consume_extract_request",
        AsyncMock(return_value={"allowed": True, "reason": None, "requests_used": None}),
    )
    monkeypatch.setattr(
        extract_service, "renew_job_claim", AsyncMock(return_value=renewed)
    )
    monkeypatch.setattr(
        extract_service, "commit_extract_job", AsyncMock(return_value=commit_status)
    )
    monkeypatch.setattr(extract_service, "get_job", AsyncMock(return_value=None))

    responses = list(llm_responses or [])

    async def fake_invoke(messages, **kwargs):
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(
        extract_service, "invoke_llm", AsyncMock(side_effect=fake_invoke)
    )
    return responses


def _committed_ok():
    call = extract_service.commit_extract_job.await_args
    assert call.args[3] == "ok"
    return call.kwargs["extract_data"], call.kwargs["engine"]


def _committed_failure():
    call = extract_service.commit_extract_job.await_args
    assert call.args[3] == "failed"
    return call.kwargs["error"]


class TestResolveSpec:
    def test_snapshot_and_revision(self):
        spec = resolve_extract_spec(_job())
        assert spec["target"] == "per_doc"
        assert spec["schema_source"] == "data_schema"
        assert spec["extraction_strategy"] == "full_document"

        revision = {"definition": {"target": "per_page", "data_schema": SCHEMA}}
        spec = resolve_extract_spec({"execution_spec": None}, revision=revision)
        assert spec["target"] == "per_page"
        assert spec["extraction_strategy"] == "full_document"

    def test_page_routed_is_valid_for_per_doc_but_not_available_by_default(self, monkeypatch):
        monkeypatch.setattr(extract_service.settings, "EXTRACT_PAGE_ROUTED_ENABLED", False)
        job = _job(execution_spec={
            "capability": "extract",
            "spec_version": "1",
            "effective_params": {
                "target": "per_doc",
                "data_schema": SCHEMA,
                "extraction_strategy": "page_routed",
            },
        })
        spec = resolve_extract_spec(job)
        assert spec["extraction_strategy"] == "page_routed"
        with pytest.raises(ExtractFailure) as exc:
            extract_service.ensure_extract_strategy_available(spec)
        assert exc.value.reason == "strategy_unavailable"

    def test_page_routed_per_page_is_rejected(self):
        job = _job(execution_spec={
            "capability": "extract",
            "spec_version": "1",
            "effective_params": {
                "target": "per_page",
                "data_schema": SCHEMA,
                "extraction_strategy": "page_routed",
            },
        })
        with pytest.raises(ExtractFailure) as exc:
            resolve_extract_spec(job)
        assert exc.value.reason == "strategy_target_not_supported"

    def test_fields_only_is_rejected_without_conversion(self):
        job = _job(execution_spec={
            "capability": "extract", "spec_version": "1",
            "effective_params": {"fields": [{"field_key": "old", "field_type": "text"}]},
        })
        with pytest.raises(ExtractFailure) as exc:
            resolve_extract_spec(job)
        assert exc.value.reason == "schema_missing"

    def test_per_table_row_rejected(self):
        job = _job(
            execution_spec={
                "capability": "extract",
                "spec_version": "1",
                "effective_params": {"target": "per_table_row", "data_schema": SCHEMA},
            }
        )
        with pytest.raises(ExtractFailure) as exc:
            resolve_extract_spec(job)
        assert exc.value.reason == "target_not_supported"

    def test_schema_missing_rejected(self):
        job = _job(
            execution_spec={
                "capability": "extract",
                "spec_version": "1",
                "effective_params": {"target": "per_doc"},
            }
        )
        with pytest.raises(ExtractFailure) as exc:
            resolve_extract_spec(job)
        assert exc.value.reason == "schema_missing"


class TestPlanUnits:
    def test_per_doc_uses_markdown_and_per_page_uses_pages(self):
        data = _parse_data(pages=2)
        doc_units = plan_units("per_doc", data)
        assert len(doc_units) == 1 and "page 1" in doc_units[0]["source"]
        page_units = plan_units("per_page", data)
        assert [unit["id"] for unit in page_units] == ["p1", "p2"]

    def test_page_source_falls_back_to_supported_blocks_in_order(self):
        data = {
            "markdown": "",
            "pages": [
                {
                    "page_no": 1,
                    "markdown": "",
                    "blocks": [
                        {"type": "text", "text": "正文"},
                        {"type": "table", "table_html": "<table>表格</table>"},
                        {"type": "formula", "latex": "x^2"},
                    ],
                },
                {"page_no": 2, "markdown": "", "blocks": []},
            ],
        }

        units = plan_units("per_page", data)

        assert units[0]["source"] == "正文\n<table>表格</table>\nx^2"
        assert units[1]["source"] == ""

    def test_page_source_keeps_table_body_when_markdown_has_caption_only(self):
        data = {
            "markdown": "",
            "pages": [{
                "page_no": 1,
                "markdown": "Table caption",
                "blocks": [{
                    "type": "table",
                    "text": "Table caption",
                    "table_html": "<table><tr><td>Phone</td><td>13800138000</td></tr></table>",
                    "reading_order": 1,
                }],
            }],
        }
        assert "13800138000" in plan_units("per_page", data)[0]["source"]


class TestValidateOutput:
    def test_per_page_reports_item_path(self):
        issues = validate_output("per_page", SCHEMA, [{"report_no": "ok"}, {"conclusion": None}])
        assert issues and issues[0]["json_path"] == "$[1]"

    def test_routed_evidence_requires_quote_and_matches_block(self):
        schema = {
            "type": "object",
            "properties": {"report_no": {"type": "string"}},
            "additionalProperties": False,
        }
        refs = {1: {"text": "page text", "blocks": {"b1": "R1 block"}}}

        accepted, _ = extract_service._validate_candidate_values(
            schema,
            {"report_no": "R1"},
            {"/report_no": [{"page_no": 1, "block_id": "b1"}]},
            ["/report_no"],
            refs,
            {},
        )
        assert accepted == {}

        accepted, _ = extract_service._validate_candidate_values(
            schema,
            {"report_no": "R1"},
            {"/report_no": [{"page_no": 1, "block_id": "b1", "quote": "R1 block"}]},
            ["/report_no"],
            refs,
            {},
        )
        assert accepted == {"/report_no": "R1"}

    def test_routed_unknown_write_path_is_rejected(self):
        schema = {
            "type": "object",
            "properties": {"report_no": {"type": "string"}},
            "additionalProperties": False,
        }
        with pytest.raises(ExtractFailure) as exc:
            extract_service._validate_candidate_values(
                schema,
                {"unknown": "value"},
                {"/unknown": [{"page_no": 1, "quote": "value"}]},
                ["/report_no"],
                {1: {"text": "value", "blocks": {}}},
                {},
            )
        assert exc.value.reason == "routed_write_path_invalid"

    @pytest.mark.parametrize("node,value,quote", [
        ({"type": ["string", "null"]}, None, "No answer in this section"),
        ({"type": "array", "items": {"type": "string"}}, [], "a few items"),
        ({"type": "number"}, 12, "Quantity 312"),
        ({"type": "number"}, -12, "Quantity 12"),
        ({"type": "string"}, "WRONG12", "Report RIGHT12"),
    ])
    def test_routed_null_empty_or_unsupported_literal_is_not_locked(self, node, value, quote):
        schema = {"type": "object", "properties": {"report_no": node}}
        accepted, _ = extract_service._validate_candidate_values(
            schema, {"report_no": value},
            {"/report_no": [{"page_no": 1, "quote": quote}]},
            ["/report_no"], {1: {"text": quote, "blocks": {}}}, {},
        )
        assert accepted == {}

    def test_repair_cannot_overwrite_locked_parent(self):
        schema = {"type": "object", "properties": {"person": {
            "type": "object", "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
        }}}
        for values in ({"person": None}, {"person": {"name": "changed"}}):
            with pytest.raises(ExtractFailure, match="field_conflict"):
                extract_service._validate_candidate_values(
                    schema, values, {}, ["/person/age"], {}, {"/person/name": "original"},
                )

    def test_candidate_page_budget_round_robins_fields_and_prefers_unexamined_pages(self):
        candidates = {
            "/phone": [PageCandidate(34, 1.0), PageCandidate(2, 0.9)],
            "/protocol": [PageCandidate(35, 1.0), PageCandidate(3, 0.9)],
        }
        first = extract_service._select_candidate_pages(candidates, 2, set())
        second = extract_service._select_candidate_pages(candidates, 2, {34, 35})
        assert first == [34, 35]
        assert second == [2, 3]


class TestHandleExtract:
    @pytest.mark.asyncio
    async def test_page_routed_runs_two_passes_and_persists_evidence(self, monkeypatch):
        schema = {
            "type": "object",
            "properties": {
                "report_no": {"type": "string"},
                "conclusion": {"type": "string"},
            },
            "required": ["report_no", "conclusion"],
            "additionalProperties": False,
        }
        parse_row = _parse_row({
            "markdown": "",
            "pages": [
                {"page_no": 1, "markdown": "R1 page", "blocks": []},
                {"page_no": 2, "markdown": "ok page", "blocks": []},
            ],
        })

        class FakePageIndex:
            async def ensure_index(self, *args, **kwargs):
                return PageIndexSnapshot(
                    tenant_id=TENANT_ID,
                    document_id=DOCUMENT_ID,
                    parse_result_id=RESULT_ID,
                    source_document_hash="source",
                    text_profile_hash="text",
                    embedding_profile_hash="embedding",
                    pages=[
                        PageIndexPage(1, "parsed", "R1 page", "t1", None, [1.0, 0.0]),
                        PageIndexPage(2, "parsed", "ok page", "t2", None, [0.0, 1.0]),
                    ],
                )

            async def retrieve(self, snapshot, *, query, **kwargs):
                page = 1 if "report_no" in query else 2
                return [PageCandidate(page, 1.0, ["vector"])]

            async def retrieve_many(self, snapshot, *, queries, **kwargs):
                return {
                    path: await self.retrieve(snapshot, query=query, **kwargs)
                    for path, query in queries.items()
                }

        _patch_env(
            monkeypatch,
            parse_row=parse_row,
            llm_responses=[
                _llm_result('{"values":{"report_no":"R1"},"evidence":{"/report_no":[{"page_no":1,"quote":"R1"}]},"unresolved":["/conclusion"]}'),
                _llm_result('{"values":{"conclusion":"ok"},"evidence":{"/conclusion":[{"page_no":2,"quote":"ok"}]},"unresolved":[]}'),
            ],
        )
        monkeypatch.setattr(extract_service.settings, "EXTRACT_PAGE_ROUTED_ENABLED", True)
        monkeypatch.setattr(extract_service, "page_index_service", FakePageIndex())
        job = _job(execution_spec={
            "capability": "extract",
            "spec_version": "1",
            "effective_params": {
                "target": "per_doc",
                "data_schema": schema,
                "extraction_strategy": "page_routed",
            },
        })

        result = await handle_extract_job(job)

        assert result == {"report_no": "R1", "conclusion": "ok"}
        payload, engine = _committed_ok()
        assert payload == result
        assert engine["extraction_strategy"] == "page_routed"
        assert engine["page_routed"]["passes"] == 2
        assert engine["page_routed"]["evidence"]["/report_no"][0]["page_no"] == 1

    @pytest.mark.asyncio
    async def test_heartbeat_error_marks_claim_lost_without_bubbling(self, monkeypatch):
        stop = extract_service.asyncio.Event()
        lost = extract_service.asyncio.Event()
        monkeypatch.setattr(
            extract_service,
            "renew_job_claim",
            AsyncMock(side_effect=RuntimeError("database unavailable")),
        )

        await asyncio.wait_for(
            extract_service._heartbeat_until(
                stop,
                lost,
                job_id=JOB_ID,
                worker_id="worker-1",
                attempts=1,
                interval=0.001,
            ),
            timeout=1,
        )

        assert lost.is_set()

    @pytest.mark.asyncio
    async def test_per_doc_happy_path(self, monkeypatch):
        captured = _patch_env(
            monkeypatch,
            llm_responses=[_llm_result('{"report_no": "WT-1", "conclusion": null}')],
        )

        payload = await handle_extract_job(_job())

        assert payload == {"report_no": "WT-1", "conclusion": None}
        data, engine = _committed_ok()
        assert data == payload
        assert engine["target"] == "per_doc"
        assert engine["extraction_strategy"] == "full_document"
        assert engine["usage"]["requests"] == 1
        assert engine["usage"]["input_tokens"] == 10
        assert captured == []

    @pytest.mark.asyncio
    async def test_per_page_units_in_order(self, monkeypatch):
        page_job = _job(
            execution_spec={
                "capability": "extract",
                "spec_version": "1",
                "effective_params": {"target": "per_page", "data_schema": SCHEMA},
            }
        )
        _patch_env(
            monkeypatch,
            parse_row=_parse_row(_parse_data(pages=2)),
            llm_responses=[
                _llm_result('{"report_no": "P1"}'),
                _llm_result('{"report_no": "P2"}'),
            ],
        )

        payload = await handle_extract_job(page_job)

        assert payload == [{"report_no": "P1"}, {"report_no": "P2"}]
        data, engine = _committed_ok()
        assert data == payload
        assert engine["usage"]["requests"] == 2

    @pytest.mark.asyncio
    async def test_second_page_failure_commits_failed_without_partial_result(self, monkeypatch):
        page_job = _job(
            execution_spec={
                "capability": "extract",
                "spec_version": "1",
                "effective_params": {"target": "per_page", "data_schema": SCHEMA},
            }
        )
        _patch_env(
            monkeypatch,
            parse_row=_parse_row(_parse_data(pages=2)),
            llm_responses=[
                _llm_result('{"report_no": "P1"}'),
                _llm_result("", finish_reason="content_filter"),
            ],
        )

        result = await handle_extract_job(page_job)

        assert result is None
        assert extract_service.invoke_llm.await_count == 2
        assert extract_service.commit_extract_job.await_args.args[3] == "failed"

    @pytest.mark.asyncio
    async def test_binding_invalid_runs_zero_llm(self, monkeypatch):
        bad_row = _parse_row()
        bad_row["document_id"] = "33333333-3333-4333-8333-333333333333"
        _patch_env(monkeypatch, parse_row=bad_row, llm_responses=[])

        result = await handle_extract_job(_job())

        assert result is None
        assert "input_binding_invalid" in _committed_failure()
        extract_service.invoke_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_parse_result_unavailable(self, monkeypatch):
        _patch_env(monkeypatch, auto_parse=False, llm_responses=[])
        monkeypatch.setattr(
            extract_service.result_service,
            "get_document_parse_result",
            AsyncMock(return_value=None),
        )

        result = await handle_extract_job(_job())

        assert result is None
        assert "parse_result_unavailable" in _committed_failure()
        extract_service.invoke_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_repair_then_success(self, monkeypatch):
        _patch_env(
            monkeypatch,
            llm_responses=[
                _llm_result('{"conclusion": null}'),
                _llm_result('{"report_no": "WT-2"}'),
            ],
        )

        payload = await handle_extract_job(_job())

        assert payload == {"report_no": "WT-2"}
        _, engine = _committed_ok()
        assert engine["usage"]["requests"] == 2

    @pytest.mark.asyncio
    async def test_repair_exhausted_fails(self, monkeypatch):
        _patch_env(
            monkeypatch,
            llm_responses=[
                _llm_result('{"conclusion": null}'),
                _llm_result('{"conclusion": "x"}'),
            ],
        )

        result = await handle_extract_job(_job())

        assert result is None
        assert "schema_validation_failed" in _committed_failure()
        assert extract_service.invoke_llm.await_count == 2

    @pytest.mark.asyncio
    async def test_truncated_response_fails_even_if_valid_json(self, monkeypatch):
        _patch_env(
            monkeypatch,
            llm_responses=[_llm_result('{"report_no": "WT-3"}', finish_reason="length")],
        )

        result = await handle_extract_job(_job())

        assert result is None
        assert "response_truncated" in _committed_failure()
        assert extract_service.invoke_llm.await_count == 1

    @pytest.mark.asyncio
    async def test_unknown_finish_reason_retries_once_then_fails(self, monkeypatch):
        _patch_env(
            monkeypatch,
            llm_responses=[
                _llm_result('{"report_no": "WT-4"}', finish_reason=None),
                _llm_result('{"report_no": "WT-4"}', finish_reason=None),
                _llm_result('{"report_no": "WT-4"}', finish_reason=None),
            ],
        )

        result = await handle_extract_job(_job())

        assert result is None
        assert "completion_unknown" in _committed_failure()
        assert extract_service.invoke_llm.await_count == 2

    @pytest.mark.asyncio
    async def test_unknown_finish_reason_recovers_after_one_protocol_retry(self, monkeypatch):
        _patch_env(
            monkeypatch,
            llm_responses=[
                _llm_result('{"report_no": "WT-4"}', finish_reason=None),
                _llm_result('{"report_no": "WT-4"}'),
            ],
        )

        payload = await handle_extract_job(_job())

        assert payload == {"report_no": "WT-4"}
        _, engine = _committed_ok()
        assert engine["usage"]["requests"] == 2

    @pytest.mark.asyncio
    async def test_transport_error_retries_within_budget(self, monkeypatch):
        _patch_env(
            monkeypatch,
            llm_responses=[
                httpx.ConnectError("connection reset"),
                _llm_result('{"report_no": "WT-5"}'),
            ],
        )

        payload = await handle_extract_job(_job())

        assert payload == {"report_no": "WT-5"}
        _, engine = _committed_ok()
        assert engine["usage"]["requests"] == 2

    @pytest.mark.asyncio
    async def test_non_transport_error_does_not_retry(self, monkeypatch):
        _patch_env(
            monkeypatch,
            llm_responses=[
                ValueError("bad client configuration"),
                _llm_result('{"report_no": "WT-5b"}'),
            ],
        )

        result = await handle_extract_job(_job())

        assert result is None
        assert "request_failed" in _committed_failure()
        assert extract_service.invoke_llm.await_count == 1

    @pytest.mark.asyncio
    async def test_transport_error_after_repair_does_not_resend(self, monkeypatch):
        _patch_env(
            monkeypatch,
            llm_responses=[
                _llm_result('{"conclusion": null}'),
                RuntimeError("connection reset"),
            ],
        )

        result = await handle_extract_job(_job())

        assert result is None
        assert "request_failed" in _committed_failure()
        assert extract_service.invoke_llm.await_count == 2

    @pytest.mark.asyncio
    async def test_unknown_on_repair_does_not_resend(self, monkeypatch):
        _patch_env(
            monkeypatch,
            llm_responses=[
                _llm_result('{"conclusion": null}'),
                _llm_result('{"report_no": "WT-6"}', finish_reason=None),
            ],
        )

        result = await handle_extract_job(_job())

        assert result is None
        assert "completion_unknown" in _committed_failure()
        assert extract_service.invoke_llm.await_count == 2

    @pytest.mark.asyncio
    async def test_refusal_fails_without_repair(self, monkeypatch):
        _patch_env(
            monkeypatch,
            llm_responses=[_llm_result("", refusal="I cannot help with that")],
        )

        result = await handle_extract_job(_job())

        assert result is None
        assert "response_refused" in _committed_failure()
        assert extract_service.invoke_llm.await_count == 1

    @pytest.mark.asyncio
    async def test_invalid_content_type_fails_without_repair(self, monkeypatch):
        _patch_env(
            monkeypatch,
            llm_responses=[_llm_result("", content_invalid=True)],
        )

        result = await handle_extract_job(_job())

        assert result is None
        assert "response_content_invalid" in _committed_failure()
        assert extract_service.invoke_llm.await_count == 1

    @pytest.mark.asyncio
    async def test_deadline_expired_before_request(self, monkeypatch):
        _patch_env(
            monkeypatch,
            llm_responses=[],
            budget={"status": "existing", "requests_used": 0, "max_requests": 200,
                    "deadline": _deadline_iso(-5)},
        )

        result = await handle_extract_job(_job())

        assert result is None
        assert "deadline_exceeded" in _committed_failure()
        extract_service.invoke_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_deadline_expired_after_response_not_accepted(self, monkeypatch):
        async def slow_invoke(messages, **kwargs):
            await asyncio.sleep(0.15)
            return _llm_result('{"report_no": "WT-7"}')

        _patch_env(monkeypatch, llm_responses=[])
        monkeypatch.setattr(extract_service, "invoke_llm", AsyncMock(side_effect=slow_invoke))
        monkeypatch.setattr(
            extract_service, "ensure_extract_budget",
            AsyncMock(return_value={"status": "initialized", "requests_used": 0,
                                    "max_requests": 200, "deadline": _deadline_iso(0.05)}),
        )

        result = await handle_extract_job(_job())

        assert result is None
        assert "deadline_exceeded" in _committed_failure()

    @pytest.mark.asyncio
    async def test_commit_response_lost_recovers_committed_result(self, monkeypatch):
        payload = {"report_no": "WT-8"}
        _patch_env(
            monkeypatch,
            llm_responses=[_llm_result('{"report_no": "WT-8"}')],
        )
        monkeypatch.setattr(
            extract_service, "commit_extract_job",
            AsyncMock(side_effect=[RuntimeError("timeout"), "completed"]),
        )
        monkeypatch.setattr(
            extract_service, "get_job",
            AsyncMock(return_value={"job_id": JOB_ID, "status": "completed"}),
        )
        monkeypatch.setattr(
            extract_service.result_service, "list_results",
            AsyncMock(return_value=[{"id": "res-1", "job_id": JOB_ID, "data": payload}]),
        )

        result = await handle_extract_job(_job())

        assert result == payload
        assert extract_service.commit_extract_job.await_count == 1

    @pytest.mark.asyncio
    async def test_commit_unconfirmed_retries_and_never_marks_failed(self, monkeypatch):
        _patch_env(
            monkeypatch,
            llm_responses=[_llm_result('{"report_no": "WT-9"}')],
        )
        monkeypatch.setattr(
            extract_service, "commit_extract_job",
            AsyncMock(side_effect=RuntimeError("timeout")),
        )
        monkeypatch.setattr(
            extract_service, "get_job",
            AsyncMock(return_value={"job_id": JOB_ID, "status": "processing"}),
        )
        monkeypatch.setattr(
            extract_service.result_service, "list_results", AsyncMock(return_value=[])
        )

        result = await handle_extract_job(_job())

        assert result is None
        assert extract_service.commit_extract_job.await_count == 2
        for call in extract_service.commit_extract_job.await_args_list:
            assert call.args[3] == "ok"

    @pytest.mark.asyncio
    async def test_commit_confirmation_job_read_error_never_marks_failed(self, monkeypatch):
        _patch_env(
            monkeypatch,
            llm_responses=[_llm_result('{"report_no": "WT-9b"}')],
        )
        monkeypatch.setattr(
            extract_service, "commit_extract_job", AsyncMock(side_effect=RuntimeError("timeout"))
        )
        monkeypatch.setattr(
            extract_service, "get_job", AsyncMock(side_effect=RuntimeError("read failed"))
        )

        result = await handle_extract_job(_job())

        assert result is None
        assert extract_service.invoke_llm.await_count == 1
        assert extract_service.commit_extract_job.await_count == 1
        assert all(call.args[3] == "ok" for call in extract_service.commit_extract_job.await_args_list)

    @pytest.mark.asyncio
    async def test_commit_confirmation_result_read_error_never_marks_failed(self, monkeypatch):
        _patch_env(
            monkeypatch,
            llm_responses=[_llm_result('{"report_no": "WT-9c"}')],
        )
        monkeypatch.setattr(
            extract_service,
            "commit_extract_job",
            AsyncMock(side_effect=RuntimeError("timeout")),
        )
        monkeypatch.setattr(
            extract_service,
            "get_job",
            AsyncMock(return_value={"job_id": JOB_ID, "status": "processing"}),
        )
        monkeypatch.setattr(
            extract_service.result_service,
            "list_results",
            AsyncMock(side_effect=RuntimeError("result read failed")),
        )

        result = await handle_extract_job(_job())

        assert result is None
        assert extract_service.invoke_llm.await_count == 1
        assert extract_service.commit_extract_job.await_count == 1
        assert all(call.args[3] == "ok" for call in extract_service.commit_extract_job.await_args_list)

    @pytest.mark.asyncio
    async def test_binding_rpc_error_recovered_by_reread(self, monkeypatch):
        parse_row = _parse_row()
        fresh = {
            "job_id": JOB_ID,
            "status": "processing",
            "locked_by": "worker-1",
            "attempts": 1,
            "document_ids": [DOCUMENT_ID],
            "parse_result_id": RESULT_ID,
        }
        _patch_env(
            monkeypatch,
            parse_row=parse_row,
            llm_responses=[_llm_result('{"report_no": "WT-10"}')],
        )
        monkeypatch.setattr(
            extract_service, "bind_extract_parse_result",
            AsyncMock(side_effect=RuntimeError("timeout")),
        )
        monkeypatch.setattr(extract_service, "get_job", AsyncMock(return_value=fresh))

        payload = await handle_extract_job(_job())

        assert payload == {"report_no": "WT-10"}
        assert extract_service.bind_extract_parse_result.await_count == 1

    @pytest.mark.asyncio
    async def test_budget_wrapper_status_not_found(self, monkeypatch):
        _patch_env(monkeypatch, llm_responses=[])
        monkeypatch.setattr(
            extract_service, "ensure_extract_budget",
            AsyncMock(return_value={"status": "stale_token"}),
        )

        result = await handle_extract_job(_job())

        assert result is None
        assert "budget_stale_token" in _committed_failure()

    @pytest.mark.asyncio
    async def test_budget_denied_before_llm(self, monkeypatch):
        _patch_env(
            monkeypatch,
            llm_responses=[],
        )
        monkeypatch.setattr(
            extract_service,
            "consume_extract_request",
            AsyncMock(return_value={"allowed": False, "reason": "deadline_exceeded"}),
        )

        result = await handle_extract_job(_job())

        assert result is None
        assert "budget_deadline_exceeded" in _committed_failure()
        assert extract_service.invoke_llm.await_count == 0

    @pytest.mark.asyncio
    async def test_context_exceeded_before_llm(self, monkeypatch):
        huge = _parse_data()
        huge["markdown"] = "中" * 10_000_000
        _patch_env(monkeypatch, parse_row=_parse_row(huge), llm_responses=[])

        result = await handle_extract_job(_job())

        assert result is None
        assert "context_exceeded" in _committed_failure()
        assert extract_service.invoke_llm.await_count == 0

    @pytest.mark.asyncio
    async def test_attempts_exceeded(self, monkeypatch):
        _patch_env(monkeypatch, llm_responses=[])

        result = await handle_extract_job(_job(attempts=3))

        assert result is None
        assert "attempts_exceeded" in _committed_failure()
        extract_service.invoke_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_claim_lost_stops_before_next_unit(self, monkeypatch):
        _patch_env(monkeypatch, llm_responses=[])
        lost = extract_service.asyncio.Event()
        lost.set()

        with pytest.raises(ExtractFailure) as exc:
            await extract_service._run_units(
                units=[{"id": "p1", "label": "页1", "source": "s"},
                       {"id": "p2", "label": "页2", "source": "s"}],
                target="per_page",
                schema=SCHEMA,
                job_id=JOB_ID,
                worker_id="worker-1",
                attempts=1,
                lost=lost,
                usage={"requests": 0},
                deadline=datetime.now(timezone.utc) + timedelta(seconds=600),
            )

        assert exc.value.reason == "claim_lost"
        assert extract_service.invoke_llm.await_count == 0

    @pytest.mark.asyncio
    async def test_claim_lost_detected_after_llm_return(self, monkeypatch):
        _patch_env(monkeypatch, llm_responses=[])
        lost = extract_service.asyncio.Event()

        async def invoke_then_lose(messages, **kwargs):
            lost.set()
            return _llm_result('{"report_no": "WT-11"}')

        monkeypatch.setattr(
            extract_service, "invoke_llm", AsyncMock(side_effect=invoke_then_lose)
        )

        with pytest.raises(ExtractFailure) as exc:
            await extract_service._run_unit(
                unit={"id": "doc", "label": "整份文档", "source": "s"},
                target="per_doc",
                schema=SCHEMA,
                job_id=JOB_ID,
                worker_id="worker-1",
                attempts=1,
                lost=lost,
                calls=[],
                usage={"requests": 0},
                deadline=datetime.now(timezone.utc) + timedelta(seconds=600),
            )

        assert exc.value.reason == "claim_lost"

    @pytest.mark.asyncio
    async def test_claim_lost_after_consume_does_not_invoke_llm(self, monkeypatch):
        _patch_env(monkeypatch, llm_responses=[])
        lost = extract_service.asyncio.Event()

        async def consume_then_lose(*args):
            lost.set()
            return {"allowed": True, "requests_used": 1}

        monkeypatch.setattr(
            extract_service, "consume_extract_request", AsyncMock(side_effect=consume_then_lose)
        )

        with pytest.raises(ExtractFailure) as exc:
            await extract_service._run_unit(
                unit={"id": "doc", "label": "整份文档", "source": "s"},
                target="per_doc",
                schema=SCHEMA,
                job_id=JOB_ID,
                worker_id="worker-1",
                attempts=1,
                lost=lost,
                calls=[],
                usage={"requests": 0},
                deadline=datetime.now(timezone.utc) + timedelta(seconds=600),
            )

        assert exc.value.reason == "claim_lost"
        assert extract_service.invoke_llm.await_count == 0

    @pytest.mark.asyncio
    async def test_deadline_during_consume_does_not_invoke_llm(self, monkeypatch):
        _patch_env(monkeypatch, llm_responses=[])
        lost = extract_service.asyncio.Event()

        async def slow_consume(*args):
            await asyncio.sleep(0.05)
            return {"allowed": True, "requests_used": 1}

        monkeypatch.setattr(
            extract_service, "consume_extract_request", AsyncMock(side_effect=slow_consume)
        )

        with pytest.raises(ExtractFailure) as exc:
            await extract_service._run_unit(
                unit={"id": "doc", "label": "整份文档", "source": "s"},
                target="per_doc",
                schema=SCHEMA,
                job_id=JOB_ID,
                worker_id="worker-1",
                attempts=1,
                lost=lost,
                calls=[],
                usage={"requests": 0},
                deadline=datetime.now(timezone.utc) + timedelta(seconds=0.01),
            )

        assert exc.value.reason == "deadline_exceeded"
        assert extract_service.invoke_llm.await_count == 0

    @pytest.mark.asyncio
    async def test_deadline_before_success_commit_does_not_commit_ok(self, monkeypatch):
        _patch_env(
            monkeypatch,
            llm_responses=[_llm_result('{"report_no": "WT-12"}')],
            budget={
                "status": "initialized",
                "requests_used": 0,
                "max_requests": 200,
                "deadline": _deadline_iso(1.0),
            },
        )

        def slow_validation(*args):
            time.sleep(1.1)
            return []

        monkeypatch.setattr(extract_service, "validate_output", slow_validation)

        result = await handle_extract_job(_job())

        assert result is None
        assert extract_service.invoke_llm.await_count == 1
        assert extract_service.commit_extract_job.await_args.args[3] == "failed"


class TestResolveSpecGuards:
    def test_snapshot_omits_missing_optional_keys(self):
        assert build_execution_spec({})["effective_params"] == {}

    def test_invalid_schema_type_not_masked_by_legacy_fields(self):
        fields = [{"field_key": "report_no", "field_label": "报告编号", "field_type": "text"}]
        job = _job(
            execution_spec={
                "capability": "extract",
                "spec_version": "1",
                "effective_params": {
                    "target": "per_doc",
                    "data_schema": [],
                    "fields": fields,
                },
            }
        )
        with pytest.raises(ExtractFailure) as exc:
            resolve_extract_spec(job)
        assert exc.value.reason == "schema_invalid"

    def test_explicit_invalid_target_is_not_defaulted(self):
        for bad_target in ("", False, "per_table_row"):
            job = _job(
                execution_spec={
                    "capability": "extract",
                    "spec_version": "1",
                    "effective_params": {"target": bad_target, "data_schema": SCHEMA},
                }
            )
            with pytest.raises(ExtractFailure) as exc:
                resolve_extract_spec(job)
            assert exc.value.reason == "target_not_supported"

    def test_explicit_null_schema_does_not_fall_back_to_legacy_fields(self):
        fields = [{"field_key": "report_no", "field_label": "报告编号", "field_type": "text"}]
        job = _job(
            execution_spec={
                "capability": "extract",
                "spec_version": "1",
                "effective_params": {
                    "target": "per_doc",
                    "data_schema": None,
                    "fields": fields,
                },
            }
        )
        with pytest.raises(ExtractFailure) as exc:
            resolve_extract_spec(job)
        assert exc.value.reason == "schema_invalid"


class TestEngineBounds:
    def test_engine_bytes_limit_keeps_calls_structure(self):
        calls = [
            {
                "unit": "p1",
                "model": "fake-model",
                "finish_reason": "stop",
                "input_tokens": 1,
                "output_tokens": 1,
                "request_id": "x" * 1200,
            }
            for _ in range(20)
        ]
        spec = {"target": "per_doc", "data_schema": SCHEMA, "schema_source": "data_schema"}
        engine = build_engine(spec, calls, 1, requests=20)

        assert isinstance(engine["usage"]["calls"], list)
        assert len(engine["usage"]["calls"]) < 20
        assert len(engine["usage"]["calls"]) <= extract_service.ENGINE_MAX_CALLS
        assert engine["usage"]["requests"] == 20
        encoded = extract_service.json.dumps(engine, ensure_ascii=False).encode("utf-8")
        assert len(encoded) <= extract_service.ENGINE_MAX_BYTES

    def test_engine_bytes_limit_counts_utf8_bytes(self):
        calls = [
            {
                "unit": "doc",
                "model": "fake-model",
                "finish_reason": "stop",
                "input_tokens": 1,
                "output_tokens": 1,
                "request_id": "请求" * 6000,
            }
        ]
        spec = {"target": "per_doc", "data_schema": SCHEMA, "schema_source": "data_schema"}

        engine = build_engine(spec, calls, 1, requests=1)

        encoded = extract_service.json.dumps(engine, ensure_ascii=False).encode("utf-8")
        assert len(encoded) <= extract_service.ENGINE_MAX_BYTES

    def test_sum_tokens_zero_is_not_missing(self):
        assert extract_service._sum_tokens([{"input_tokens": 0}], "input_tokens") == 0
        assert extract_service._sum_tokens(
            [{"input_tokens": 0}, {"input_tokens": None}], "input_tokens"
        ) is None
        assert extract_service._sum_tokens([], "input_tokens") is None

    def test_unreported_requests_keep_top_level_tokens_unknown(self):
        calls = [{"unit": "doc", "input_tokens": 10, "output_tokens": 5}]
        spec = {"target": "per_doc", "data_schema": SCHEMA, "schema_source": "data_schema"}

        engine = build_engine(spec, calls, 1, requests=2)

        assert engine["usage"]["input_tokens"] is None
        assert engine["usage"]["output_tokens"] is None
