# tests/routes/test_helpers.py
"""文档路由辅助函数测试 — validate_file_extension、normalize_review_value、parse_allowed_values"""

import pytest
from unittest.mock import patch


# ============ validate_file_extension ============

class TestValidateFileExtension:
    """文件扩展名校验"""

    def test_pdf_allowed(self):
        from api.routes.documents.helpers import validate_file_extension
        with patch("api.routes.documents.helpers.settings") as mock_settings:
            mock_settings.allowed_extensions_list = [".pdf", ".jpg", ".png"]
            assert validate_file_extension("report.pdf") is True

    def test_jpg_allowed(self):
        from api.routes.documents.helpers import validate_file_extension
        with patch("api.routes.documents.helpers.settings") as mock_settings:
            mock_settings.allowed_extensions_list = [".pdf", ".jpg", ".png"]
            assert validate_file_extension("photo.jpg") is True

    def test_exe_rejected(self):
        from api.routes.documents.helpers import validate_file_extension
        with patch("api.routes.documents.helpers.settings") as mock_settings:
            mock_settings.allowed_extensions_list = [".pdf", ".jpg", ".png"]
            assert validate_file_extension("virus.exe") is False

    def test_no_extension_rejected(self):
        from api.routes.documents.helpers import validate_file_extension
        with patch("api.routes.documents.helpers.settings") as mock_settings:
            mock_settings.allowed_extensions_list = [".pdf", ".jpg"]
            assert validate_file_extension("noext") is False

    def test_case_insensitive(self):
        from api.routes.documents.helpers import validate_file_extension
        with patch("api.routes.documents.helpers.settings") as mock_settings:
            mock_settings.allowed_extensions_list = [".pdf", ".jpg"]
            assert validate_file_extension("REPORT.PDF") is True

    def test_double_extension(self):
        from api.routes.documents.helpers import validate_file_extension
        with patch("api.routes.documents.helpers.settings") as mock_settings:
            mock_settings.allowed_extensions_list = [".pdf"]
            assert validate_file_extension("file.tar.pdf") is True


# ============ normalize_review_value ============

class TestNormalizeReviewValue:
    """审核值标准化"""

    def test_normal_string(self):
        from api.routes.documents.helpers import normalize_review_value
        assert normalize_review_value("合格") == "合格"

    def test_strips_whitespace(self):
        from api.routes.documents.helpers import normalize_review_value
        assert normalize_review_value("  合格  ") == "合格"

    def test_casefold(self):
        from api.routes.documents.helpers import normalize_review_value
        assert normalize_review_value("PASS") == "pass"

    def test_none_returns_empty(self):
        from api.routes.documents.helpers import normalize_review_value
        assert normalize_review_value(None) == ""

    def test_number_to_string(self):
        from api.routes.documents.helpers import normalize_review_value
        assert normalize_review_value(42) == "42"

    def test_bool_to_string(self):
        from api.routes.documents.helpers import normalize_review_value
        assert normalize_review_value(True) == "true"


# ============ parse_allowed_values ============

class TestParseAllowedValues:
    """允许值列表解析"""

    def test_list_input(self):
        from api.routes.documents.helpers import parse_allowed_values
        assert parse_allowed_values(["合格", "不合格"]) == ["合格", "不合格"]

    def test_json_string_input(self):
        from api.routes.documents.helpers import parse_allowed_values
        assert parse_allowed_values('["合格", "不合格"]') == ["合格", "不合格"]

    def test_plain_string_input(self):
        from api.routes.documents.helpers import parse_allowed_values
        assert parse_allowed_values("合格") == ["合格"]

    def test_none_returns_empty(self):
        from api.routes.documents.helpers import parse_allowed_values
        assert parse_allowed_values(None) == []

    def test_empty_string_returns_empty(self):
        from api.routes.documents.helpers import parse_allowed_values
        assert parse_allowed_values("") == []

    def test_list_with_none_items_filtered(self):
        from api.routes.documents.helpers import parse_allowed_values
        assert parse_allowed_values(["合格", None, "不合格"]) == ["合格", "不合格"]

    def test_number_input(self):
        from api.routes.documents.helpers import parse_allowed_values
        assert parse_allowed_values(42) == ["42"]

    def test_invalid_json_string(self):
        from api.routes.documents.helpers import parse_allowed_values
        assert parse_allowed_values("{not json}") == ["{not json}"]
