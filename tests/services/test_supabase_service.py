# tests/services/test_supabase_service.py
"""SupabaseService 单元测试 — 纯逻辑方法（日期清洗、单位修正、显示名生成等）"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from datetime import datetime

from loguru import logger

from services.supabase_service import SupabaseService


@pytest.fixture
def svc():
    """返回一个注入了 mock client 的 SupabaseService 实例"""
    instance = SupabaseService()
    instance._client = MagicMock()
    return instance


# ============ _validate_and_fix_date ============

class TestLoggingSafety:
    """异常日志稳定性"""

    @pytest.mark.asyncio
    async def test_create_document_logs_exception_with_braces_without_secondary_error(self, svc):
        """创建文档失败时，异常消息含大括号也不会触发日志二次报错"""
        svc._client.table.side_effect = Exception(
            "{'code': 'PGRST204', 'message': \"Column push_attachment does not exist\"}"
        )

        with patch.object(logger, "error") as mock_logger_error:
            with pytest.raises(Exception, match="PGRST204"):
                await svc.create_document({"id": "doc-001", "push_attachment": True})

        mock_logger_error.assert_called_once()


class TestAsyncOffloading:
    @pytest.mark.asyncio
    async def test_get_document_uses_run_sync_for_blocking_execute(self, svc):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.execute.return_value = MagicMock(data=[{"id": "doc-1"}])
        svc._client.table.return_value = chain

        with patch.object(svc, "_run_sync", new_callable=AsyncMock) as mock_run_sync:
            mock_run_sync.side_effect = lambda fn, *args, **kwargs: fn(*args, **kwargs)
            result = await svc.get_document("doc-1")

        assert result == {"id": "doc-1"}
        mock_run_sync.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_extraction_result_awaits_async_column_lookup(self, svc):
        chain = MagicMock()
        chain.upsert.return_value = chain
        chain.execute.return_value = MagicMock(data=[{"document_id": "doc-1"}])
        svc._client.table.return_value = chain

        with patch("services.schema_sync_service.schema_sync_service.get_columns", new_callable=AsyncMock, return_value={"document_id", "raw_extraction_data", "sample_name"}) as mock_get_columns:
            result = await svc.save_inspection_report("doc-1", {"sample_name": "样品A"})

        assert result == {"document_id": "doc-1"}
        mock_get_columns.assert_awaited_once_with("inspection_reports")


class TestValidateAndFixDate:
    """日期格式校验与修复"""

    def test_standard_format(self, svc):
        """标准 YYYY-MM-DD 直接返回"""
        assert svc._validate_and_fix_date("2025-03-16") == "2025-03-16"

    def test_slash_format(self, svc):
        """YYYY/MM/DD 转换为标准格式"""
        assert svc._validate_and_fix_date("2025/03/16") == "2025-03-16"

    def test_dot_format(self, svc):
        """YYYY.MM.DD 转换为标准格式"""
        assert svc._validate_and_fix_date("2025.03.16") == "2025-03-16"

    def test_chinese_format(self, svc):
        """YYYY年MM月DD日 转换为标准格式"""
        assert svc._validate_and_fix_date("2025年03月16日") == "2025-03-16"

    def test_compact_format(self, svc):
        """YYYYMMDD 8位数字格式"""
        assert svc._validate_and_fix_date("20250316") == "2025-03-16"

    def test_trailing_noise(self, svc):
        """OCR 尾部噪声字符被清理"""
        assert svc._validate_and_fix_date("2025-03-16//") == "2025-03-16"

    def test_leading_noise(self, svc):
        """OCR 头部噪声字符被清理"""
        assert svc._validate_and_fix_date("--2025-03-16") == "2025-03-16"

    def test_whitespace(self, svc):
        """前后空白被清理"""
        assert svc._validate_and_fix_date("  2025-03-16  ") == "2025-03-16"

    def test_invalid_format_returns_none(self, svc):
        """无效格式返回 None"""
        assert svc._validate_and_fix_date("not-a-date") is None

    def test_empty_string_returns_none(self, svc):
        """空字符串返回 None"""
        assert svc._validate_and_fix_date("") is None

    def test_none_returns_none(self, svc):
        """None 返回 None"""
        assert svc._validate_and_fix_date(None) is None

    def test_year_only_returns_none(self, svc):
        """仅年份返回 None"""
        assert svc._validate_and_fix_date("2025") is None

    def test_non_string_returns_none(self, svc):
        """非字符串返回 None"""
        assert svc._validate_and_fix_date(12345) is None


# ============ _clean_data_for_db ============

class TestCleanDataForDb:
    """数据库入库前数据清洗"""

    def test_empty_date_becomes_none(self, svc):
        """空字符串日期字段转为 None"""
        data = {"sampling_date": "", "sample_name": "测试样品"}
        cleaned = svc._clean_data_for_db(data, "sampling_forms")
        assert cleaned["sampling_date"] is None
        assert cleaned["sample_name"] == "测试样品"

    def test_valid_date_normalized(self, svc):
        """有效日期被标准化"""
        data = {"sampling_date": "2025/03/16"}
        cleaned = svc._clean_data_for_db(data, "sampling_forms")
        assert cleaned["sampling_date"] == "2025-03-16"

    def test_invalid_date_becomes_none(self, svc):
        """无效日期转为 None"""
        data = {"report_date": "无日期"}
        cleaned = svc._clean_data_for_db(data, "inspection_reports")
        assert cleaned["report_date"] is None

    def test_non_date_field_untouched(self, svc):
        """非日期字段不受影响"""
        data = {"sample_name": "LED灯", "report_date": "2025-03-16"}
        cleaned = svc._clean_data_for_db(data, "inspection_reports")
        assert cleaned["sample_name"] == "LED灯"

    def test_production_date_batch_excluded(self, svc):
        """NON_DATE_FIELDS 中的字段不做日期校验"""
        data = {"production_date_batch": "2025年第3批"}
        cleaned = svc._clean_data_for_db(data, "inspection_reports")
        assert cleaned["production_date_batch"] == "2025年第3批"

    def test_original_data_not_mutated(self, svc):
        """原始数据不被修改"""
        data = {"sampling_date": "2025/03/16"}
        svc._clean_data_for_db(data, "sampling_forms")
        assert data["sampling_date"] == "2025/03/16"


# ============ _normalize_lighting_units ============

class TestNormalizeLightingUnits:
    """OCR 单位修正"""

    def test_1m_w_to_lm_w(self, svc):
        """1m/W → lm/W"""
        data = {"luminous_flux": "1200 1m/W"}
        result = svc._normalize_lighting_units(data)
        assert "lm/W" in result["luminous_flux"]

    def test_number_followed_by_1m(self, svc):
        """数字后的 1m → lm"""
        data = {"luminous_flux": "1200 1m"}
        result = svc._normalize_lighting_units(data)
        assert "1200 lm" in result["luminous_flux"] or "1200lm" in result["luminous_flux"]

    def test_none_data_returns_none(self, svc):
        """None 输入返回 None"""
        assert svc._normalize_lighting_units(None) is None

    def test_empty_dict_returns_empty(self, svc):
        """空字典返回空字典"""
        assert svc._normalize_lighting_units({}) == {}

    def test_non_target_field_untouched(self, svc):
        """非目标字段不受影响"""
        data = {"sample_name": "1m LED灯"}
        result = svc._normalize_lighting_units(data)
        assert result["sample_name"] == "1m LED灯"


# ============ generate_display_name ============

class TestGenerateDisplayName:
    """文档显示名称生成"""

    def test_inspection_report_with_sample(self, svc):
        """检测报告：报告_{样品名称}_{规格型号}_{日期}"""
        data = {
            "sample_name": "LED灯泡",
            "specification_model": "E27-10W",
            "sampling_date": "2025-03-16",
        }
        name = svc.generate_display_name("inspection_report", data)
        assert name.startswith("报告_")
        assert "LED灯泡" in name
        assert "E27-10W" in name

    def test_inspection_report_chinese_type(self, svc):
        """检测报告（中文类型名）"""
        data = {"sample_name": "灯管"}
        name = svc.generate_display_name("检测报告", data)
        assert "报告" in name
        assert "灯管" in name

    def test_express_with_tracking(self, svc):
        """快递单：快递_{快递单号}_{收件人}"""
        data = {"tracking_number": "SF1234567890", "recipient": "张三"}
        name = svc.generate_display_name("express", data)
        assert "快递" in name

    def test_sampling_form(self, svc):
        """抽样单：抽样_{产品名称}_{省份城市}"""
        data = {"product_name": "LED灯", "province_city": "广东深圳"}
        name = svc.generate_display_name("sampling_form", data)
        assert "抽样" in name

    def test_unknown_type_fallback(self, svc):
        """未知类型使用时间戳兜底"""
        name = svc.generate_display_name("unknown_type", {})
        assert "文档_" in name

    def test_empty_extraction_data(self, svc):
        """提取数据为空时使用兜底"""
        name = svc.generate_display_name("inspection_report", {})
        # 没有 sample_name，走兜底逻辑
        assert "报告" in name or "文档" in name

    def test_exception_returns_fallback(self, svc):
        """异常时返回兜底名称"""
        name = svc.generate_display_name("inspection_report", None)
        assert "文档_" in name


class TestResetStuckProcessing:
    @pytest.mark.asyncio
    async def test_reset_stuck_returns_count_of_affected_documents(self):
        """超过超时阈值的 processing 文档应被重置为 failed，返回受影响数量"""
        from services.supabase_service import SupabaseService
        svc = SupabaseService()

        fake_stuck = [
            {"id": "doc-stuck-1", "status": "processing"},
            {"id": "doc-stuck-2", "status": "processing"},
        ]

        # select 返回两条卡死记录
        select_chain = MagicMock()
        select_chain.select.return_value = select_chain
        select_chain.eq.return_value = select_chain
        select_chain.lt.return_value = select_chain
        select_chain.execute.return_value = MagicMock(data=fake_stuck)
        # update 返回空
        update_chain = MagicMock()
        update_chain.update.return_value = update_chain
        update_chain.in_.return_value = update_chain
        update_chain.execute.return_value = MagicMock(data=[])

        mock_client = MagicMock()
        mock_client.table.side_effect = [select_chain, update_chain]
        svc._client = mock_client

        with patch.object(svc, "_run_sync", side_effect=lambda fn: fn()):
            count = await svc.reset_stuck_processing_documents(timeout_minutes=30)

        assert count == 2
        # 确认调了 update，并且状态改为 failed
        update_chain.update.assert_called_once()
        payload = update_chain.update.call_args.args[0]
        assert payload["status"] == "failed"
        assert "error_message" in payload
