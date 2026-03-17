# tests/routes/test_health.py
"""健康检查路由测试 — GET /api/health、/api/health/ocr、/api/health/config"""

import pytest
from unittest.mock import patch, MagicMock


class TestHealthCheck:
    """GET /api/health"""

    def test_health_returns_200(self, client):
        """健康检查返回 200"""
        with patch("api.routes.health.ocr_service") as mock_ocr:
            mock_ocr.ocr_engine = None
            resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_health_response_has_status(self, client):
        """响应体包含 status 字段"""
        with patch("api.routes.health.ocr_service") as mock_ocr:
            mock_ocr.ocr_engine = MagicMock()
            resp = client.get("/api/health")
        data = resp.json()
        assert "status" in data
        assert data["status"] == "healthy"

    def test_health_response_has_timestamp(self, client):
        """响应体包含 timestamp 字段"""
        with patch("api.routes.health.ocr_service") as mock_ocr:
            mock_ocr.ocr_engine = MagicMock()
            resp = client.get("/api/health")
        data = resp.json()
        assert "timestamp" in data

    def test_health_response_has_services(self, client):
        """响应体包含 services 字段"""
        with patch("api.routes.health.ocr_service") as mock_ocr:
            mock_ocr.ocr_engine = MagicMock()
            resp = client.get("/api/health")
        data = resp.json()
        assert "services" in data

    def test_health_ocr_not_initialized(self, client):
        """OCR 未初始化时 services.ocr 为 not_initialized"""
        with patch("api.routes.health.ocr_service") as mock_ocr:
            mock_ocr.ocr_engine = None
            resp = client.get("/api/health")
        data = resp.json()
        assert data["services"]["ocr"] == "not_initialized"

    def test_health_ocr_ready(self, client):
        """OCR 已初始化时 services.ocr 为 ready"""
        with patch("api.routes.health.ocr_service") as mock_ocr:
            mock_ocr.ocr_engine = MagicMock()  # 非 None
            resp = client.get("/api/health")
        data = resp.json()
        assert data["services"]["ocr"] == "ready"


class TestOcrHealth:
    """GET /api/health/ocr"""

    def test_ocr_health_returns_200(self, client):
        """OCR 健康检查返回 200"""
        with patch("api.routes.health.ocr_service") as mock_ocr:
            mock_ocr.ocr_engine = MagicMock()
            resp = client.get("/api/health/ocr")
        assert resp.status_code == 200

    def test_ocr_health_has_service_field(self, client):
        """响应体包含 service 字段"""
        with patch("api.routes.health.ocr_service") as mock_ocr:
            mock_ocr.ocr_engine = MagicMock()
            resp = client.get("/api/health/ocr")
        data = resp.json()
        assert data["service"] == "ocr"

    def test_ocr_health_has_status(self, client):
        """响应体包含 status 字段"""
        with patch("api.routes.health.ocr_service") as mock_ocr:
            mock_ocr.ocr_engine = MagicMock()
            resp = client.get("/api/health/ocr")
        data = resp.json()
        assert "status" in data
        assert data["status"] in ("ready", "not_initialized")

    def test_ocr_health_has_models_exist(self, client):
        """响应体包含 models_exist 字段"""
        with patch("api.routes.health.ocr_service") as mock_ocr:
            mock_ocr.ocr_engine = MagicMock()
            resp = client.get("/api/health/ocr")
        data = resp.json()
        assert "models_exist" in data

    def test_ocr_health_has_models_paths(self, client):
        """响应体包含 models 路径字段"""
        with patch("api.routes.health.ocr_service") as mock_ocr:
            mock_ocr.ocr_engine = MagicMock()
            resp = client.get("/api/health/ocr")
        data = resp.json()
        assert "models" in data
        models = data["models"]
        assert "det" in models
        assert "rec" in models

    def test_ocr_not_initialized_status(self, client):
        """OCR 引擎为 None 时 status 为 not_initialized"""
        with patch("api.routes.health.ocr_service") as mock_ocr:
            mock_ocr.ocr_engine = None
            resp = client.get("/api/health/ocr")
        data = resp.json()
        assert data["status"] == "not_initialized"


class TestConfigCheck:
    """GET /api/health/config"""

    def test_config_returns_200(self, client):
        """配置检查返回 200"""
        resp = client.get("/api/health/config")
        assert resp.status_code == 200

    def test_config_has_app_name(self, client):
        """响应体包含 app_name"""
        resp = client.get("/api/health/config")
        data = resp.json()
        assert "app_name" in data

    def test_config_has_llm_model(self, client):
        """响应体包含 llm_model"""
        resp = client.get("/api/health/config")
        data = resp.json()
        assert "llm_model" in data

    def test_config_has_allowed_extensions(self, client):
        """响应体包含 allowed_extensions"""
        resp = client.get("/api/health/config")
        data = resp.json()
        assert "allowed_extensions" in data

    def test_config_has_max_file_size(self, client):
        """响应体包含 max_file_size"""
        resp = client.get("/api/health/config")
        data = resp.json()
        assert "max_file_size" in data

    def test_config_has_upload_folder(self, client):
        """响应体包含 upload_folder"""
        resp = client.get("/api/health/config")
        data = resp.json()
        assert "upload_folder" in data
