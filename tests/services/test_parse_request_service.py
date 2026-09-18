# tests/services/test_parse_request_service.py
"""Parse 受理服务单测：参数规范化、请求指纹与执行规格（不依赖数据库）。"""

import pytest

from config.settings import settings
from services.parse_request_service import (
    ParseRequestError,
    build_execution_spec,
    build_request_fingerprint,
    compact_target_pages,
    normalize_document_ids,
    normalize_parse_options,
    normalize_target_pages,
    resolve_parse_mode,
)


class TestTargetPages:
    def test_none_and_blank_mean_all_pages(self):
        assert normalize_target_pages(None) is None
        assert normalize_target_pages("   ") is None

    def test_single_pages_and_ranges_normalize_sorted_deduped(self):
        assert normalize_target_pages("5,1,3-4,2") == [1, 2, 3, 4, 5]
        assert normalize_target_pages("2,2") == [2]

    def test_reversed_range_rejected(self):
        with pytest.raises(ParseRequestError) as exc:
            normalize_target_pages("10-5")
        assert exc.value.reason == "invalid_target_pages"

    def test_non_positive_and_malformed_rejected(self):
        for raw in ("0", "-3", "a", "1..3", "1,"):
            with pytest.raises(ParseRequestError):
                normalize_target_pages(raw)

    def test_range_size_cap(self, monkeypatch):
        monkeypatch.setattr(settings, "PARSE_MAX_TARGET_PAGES", 10)
        with pytest.raises(ParseRequestError):
            normalize_target_pages("1-11")

    def test_compact_pages(self):
        assert compact_target_pages([1, 3, 5, 6, 7, 10]) == "1,3,5-7,10"
        assert compact_target_pages(None) is None


class TestParseMode:
    def test_default_mode_is_policy_default(self):
        assert resolve_parse_mode(None) == "pipeline"

    def test_explicit_mode(self):
        assert resolve_parse_mode("vlm") == "vlm"

    def test_unsupported_mode_rejected(self):
        with pytest.raises(ParseRequestError):
            resolve_parse_mode("agentic")


class TestParseOptions:
    def test_defaults_are_not_injected(self):
        assert normalize_parse_options() == {}

    def test_provided_options_are_kept(self):
        assert normalize_parse_options(
            language="en",
            enable_formula=False,
            enable_table=True,
            remove_watermark=True,
            watermark_keywords=["COPY", " COPY ", "样本", "样本", "  "],
        ) == {
            "language": "en",
            "enable_formula": False,
            "enable_table": True,
            "remove_watermark": True,
            "watermark_keywords": ["COPY", "样本"],
        }

    def test_blank_keyword_list_is_not_injected(self):
        assert normalize_parse_options(watermark_keywords=["  ", ""]) == {}

    def test_too_many_keywords_rejected(self):
        with pytest.raises(ParseRequestError) as exc:
            normalize_parse_options(watermark_keywords=[f"kw-{i}" for i in range(21)])
        assert exc.value.reason == "too_many_watermark_keywords"

    def test_language_is_trimmed(self):
        assert normalize_parse_options(language="  ch  ") == {"language": "ch"}

    def test_unsupported_language_rejected(self):
        with pytest.raises(ParseRequestError) as exc:
            normalize_parse_options(language="klingon")
        assert exc.value.reason == "unsupported_language"


class TestExecutionSpec:
    def test_spec_freezes_effective_params_and_selection(self):
        spec = build_execution_spec(parse_mode="vlm", target_pages=[1, 3, 4])

        assert spec["capability"] == "parse"
        assert spec["spec_version"] == "1"
        assert spec["policy_version"] == settings.PARSE_POLICY_VERSION
        assert spec["input_selection"] == {"target_pages": [1, 3, 4]}
        assert spec["effective_params"]["model_version"] == "vlm"
        assert spec["effective_params"]["page_ranges"] == "1,3-4"

    def test_default_spec_has_no_page_ranges(self):
        spec = build_execution_spec(parse_mode="pipeline", target_pages=None)
        assert spec["effective_params"]["page_ranges"] is None

    def test_options_override_defaults(self):
        spec = build_execution_spec(
            parse_mode="pipeline",
            target_pages=None,
            options={"language": "en", "enable_formula": False, "enable_table": False},
        )
        params = spec["effective_params"]
        assert params["language"] == "en"
        assert params["enable_formula"] is False
        assert params["enable_table"] is False

    def test_remove_watermark_defaults_off(self):
        spec = build_execution_spec(parse_mode="pipeline", target_pages=None)
        assert spec["effective_params"]["remove_watermark"] is False
        assert spec["effective_params"]["watermark_keywords"] == []

    def test_options_do_not_override_mode_or_pages(self):
        spec = build_execution_spec(
            parse_mode="vlm",
            target_pages=[2],
            options={"language": "en"},
        )
        assert spec["effective_params"]["model_version"] == "vlm"
        assert spec["effective_params"]["page_ranges"] == "2"


class TestFingerprint:
    def test_fingerprint_is_order_insensitive(self):
        first = build_request_fingerprint(
            document_ids=["b", "a"], requested_mode=None, target_pages=None
        )
        second = build_request_fingerprint(
            document_ids=["a", "b"], requested_mode=None, target_pages=None
        )
        assert first == second

    def test_fingerprint_distinguishes_mode_and_pages(self):
        base = build_request_fingerprint(
            document_ids=["a"], requested_mode=None, target_pages=None
        )
        assert base != build_request_fingerprint(
            document_ids=["a"], requested_mode="vlm", target_pages=None
        )
        assert base != build_request_fingerprint(
            document_ids=["a"], requested_mode=None, target_pages=[1]
        )

    def test_fingerprint_distinguishes_options(self):
        base = build_request_fingerprint(
            document_ids=["a"], requested_mode=None, target_pages=None
        )
        assert base == build_request_fingerprint(
            document_ids=["a"], requested_mode=None, target_pages=None, options=None
        )
        assert base == build_request_fingerprint(
            document_ids=["a"], requested_mode=None, target_pages=None, options={}
        )
        assert base != build_request_fingerprint(
            document_ids=["a"], requested_mode=None, target_pages=None,
            options={"language": "en"},
        )
        assert base != build_request_fingerprint(
            document_ids=["a"], requested_mode=None, target_pages=None,
            options={"enable_formula": False},
        )
        assert base != build_request_fingerprint(
            document_ids=["a"], requested_mode=None, target_pages=None,
            options={"remove_watermark": True},
        )
        assert base != build_request_fingerprint(
            document_ids=["a"], requested_mode=None, target_pages=None,
            options={"watermark_keywords": ["COPY"]},
        )

    def test_fingerprint_does_not_depend_on_effective_defaults(self, monkeypatch):
        from services import parse_request_service

        before = build_request_fingerprint(
            document_ids=["a"], requested_mode=None, target_pages=None
        )
        monkeypatch.setattr(
            parse_request_service,
            "PARSE_DEFAULTS",
            {"backend": "other-backend", "model_version": "pipeline"},
        )
        after = build_request_fingerprint(
            document_ids=["a"], requested_mode=None, target_pages=None
        )
        assert before == after


class TestDocumentIds:
    def test_dedup_and_sorted(self):
        assert normalize_document_ids(["b", "a", "b"]) == ["a", "b"]

    def test_empty_rejected(self):
        with pytest.raises(ParseRequestError):
            normalize_document_ids([])

    def test_cap_rejected(self, monkeypatch):
        monkeypatch.setattr(settings, "PARSE_MAX_FILES_PER_REQUEST", 2)
        with pytest.raises(ParseRequestError) as exc:
            normalize_document_ids(["a", "b", "c"])
        assert exc.value.reason == "max_files_per_request"


class TestAdmitPayload:
    @pytest.mark.asyncio
    async def test_admit_calls_rpc_with_frozen_spec(self, monkeypatch):
        from services import parse_request_service as module

        captured = {}

        class FakeRpc:
            def execute(self):
                return type("R", (), {"data": [{
                    "out_status": "ok",
                    "out_request_id": "req-1",
                    "out_job_ids": ["job-1"],
                    "out_reason": None,
                }]})

        class FakeClient:
            def rpc(self, name, payload):
                captured["name"] = name
                captured["payload"] = payload
                return FakeRpc()

        service = module.ParseRequestService()
        monkeypatch.setattr(service, "_client", FakeClient())
        monkeypatch.setattr(settings, "PARSE_POLICY_VERSION", "policy-x")

        result = await service.admit(
            tenant_id="tenant-1",
            requester_id="user-1",
            is_admin=False,
            document_ids=["doc-1"],
            parse_mode=None,
            target_pages=[1, 2],
            idempotency_key="K1",
            options={"language": "en", "enable_formula": False},
        )

        assert captured["name"] == "admit_parse_request"
        payload = captured["payload"]
        assert payload["p_tenant_id"] == "tenant-1"
        assert payload["p_is_admin"] is False
        assert payload["p_idempotency_key"] == "K1"
        assert payload["p_policy_version"] == "policy-x"
        assert payload["p_spec"]["effective_params"]["model_version"] == "pipeline"
        assert payload["p_spec"]["effective_params"]["language"] == "en"
        assert payload["p_spec"]["effective_params"]["enable_formula"] is False
        assert payload["p_spec"]["effective_params"]["enable_table"] is True
        assert payload["p_spec"]["input_selection"] == {"target_pages": [1, 2]}
        assert payload["p_max_files"] == settings.PARSE_MAX_FILES_PER_REQUEST
        assert result["status"] == "ok"
        assert result["job_ids"] == ["job-1"]
