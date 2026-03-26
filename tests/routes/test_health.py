# tests/routes/test_health.py
"""健康检查路由测试 — GET /api/health、/api/health/ocr、/api/health/jobs、/api/health/config"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


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


class TestHttpExceptionHandler:
    """HTTP 异常处理器"""

    @pytest.mark.asyncio
    async def test_handles_dict_detail_with_braces(self):
        """detail 为 dict 时也应正常返回 4xx 而非日志二次报错"""
        from api.main import http_exception_handler

        response = await http_exception_handler(
            MagicMock(),
            HTTPException(
                status_code=400,
                detail={"code": "PGRST204", "message": "Column 'push_attachment' does not exist"},
            ),
        )

        assert response.status_code == 400
        assert json.loads(response.body) == {
            "error": {"code": "PGRST204", "message": "Column 'push_attachment' does not exist"},
            "code": "HTTP_ERROR",
            "status_code": 400,
        }


class TestGeneralExceptionHandler:
    """全局异常处理器"""

    @pytest.mark.asyncio
    async def test_handles_exception_message_with_braces(self):
        """异常消息包含大括号时也应正常返回 500"""
        from api.main import general_exception_handler

        response = await general_exception_handler(
            MagicMock(),
            Exception("{'code': 'PGRST204', 'message': \"Column 'push_attachment' does not exist\"}"),
        )

        assert response.status_code == 500
        assert json.loads(response.body) == {
            "error": "内部服务器错误",
            "code": "INTERNAL_ERROR",
        }


class TestJobsHealth:
    """GET /api/health/jobs"""

    def test_jobs_health_returns_metrics(self, client):
        with patch("api.routes.health.supabase_service.get_job_metrics", new_callable=MagicMock) as mock_metrics:
            mock_metrics.return_value = {
                "active_jobs": 3,
                "failed_jobs": 1,
                "completed_jobs": 8,
                "avg_queue_seconds": 42,
                "sample_size": 5,
                "recommended_action": "stay_on_current_architecture",
                "escalation_reasons": [],
                "observed_at": "2026-03-25T00:00:00",
            }
            resp = client.get("/api/health/jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_jobs"] == 3
        assert data["recommended_action"] == "stay_on_current_architecture"


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
