# tests/agents/test_workflow.py
"""OCRWorkflow 单元测试 — mock LLM / OCR，验证节点逻辑和流程编排"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.exceptions import WorkflowError, WorkflowErrorType


# ============ fixtures ============

@pytest.fixture
def workflow():
    """构造 OCRWorkflow 实例，mock 掉 LLM 和外部服务"""
    with patch("agents.workflow.ChatOpenAI") as MockLLM, \
         patch("agents.workflow.MemorySaver"):
        mock_llm = MagicMock()
        MockLLM.return_value = mock_llm
        from agents.workflow import OCRWorkflow
        wf = OCRWorkflow()
        wf.llm = mock_llm
        return wf


def _base_state(**overrides):
    """构造基础 WorkflowState"""
    state = {
        "messages": [],
        "document_id": "doc-001",
        "file_path": "/tmp/test.pdf",
        "ocr_text": "",
        "ocr_confidence": 0.0,
        "document_type": "inspection_report",
        "extraction_data": {},
        "step": "init",
        "error": None,
        "processing_start": None,
        "tenant_id": "tenant-001",
    }
    state.update(overrides)
    return state


# ============ _ocr_node ============

class TestOcrNode:
    """OCR 节点测试"""

    @pytest.mark.asyncio
    async def test_ocr_success(self, workflow):
        """OCR 成功返回文本和置信度"""
        state = _base_state()
        with patch("agents.workflow.ocr_service") as mock_ocr:
            mock_ocr.process_document = AsyncMock(return_value={
                "text": "样品编号：SN-001",
                "confidence": 0.95,
                "total_lines": 5,
            })
            result = await workflow._ocr_node(state)
        assert result["ocr_text"] == "样品编号：SN-001"
        assert result["ocr_confidence"] == 0.95
        assert result["step"] == "ocr_completed"

    @pytest.mark.asyncio
    async def test_ocr_empty_path_raises(self, workflow):
        """文件路径为空时抛出 VALIDATION_ERROR"""
        state = _base_state(file_path="")
        with pytest.raises(WorkflowError) as exc_info:
            await workflow._ocr_node(state)
        assert exc_info.value.error_type == WorkflowErrorType.VALIDATION_ERROR

    @pytest.mark.asyncio
    async def test_ocr_service_failure(self, workflow):
        """OCR 服务异常时抛出 OCR_FAILED"""
        state = _base_state()
        with patch("agents.workflow.ocr_service") as mock_ocr:
            mock_ocr.process_document = AsyncMock(side_effect=RuntimeError("OCR引擎崩溃"))
            with pytest.raises(WorkflowError) as exc_info:
                await workflow._ocr_node(state)
        assert exc_info.value.error_type == WorkflowErrorType.OCR_FAILED


# ============ _extract_node ============

class TestExtractNode:
    """字段提取节点测试"""

    @pytest.mark.asyncio
    async def test_extract_success(self, workflow):
        """正常提取返回结构化数据"""
        state = _base_state(ocr_text="样品编号：SN-001\n样品名称：LED灯")
        mock_template = {"id": "t1", "name": "检测报告", "code": "inspection_report"}

        workflow.llm.ainvoke = AsyncMock(return_value=MagicMock(
            content='{"sample_name": "LED灯", "sample_number": "SN-001"}'
        ))

        with patch("agents.workflow.template_service") as mock_ts:
            mock_ts.get_template_by_code = AsyncMock(return_value=mock_template)
            mock_ts.build_extraction_prompt.return_value = "提取以下字段..."
            result = await workflow._extract_node(state)

        assert result["extraction_data"]["sample_name"] == "LED灯"
        assert result["step"] == "completed"

    @pytest.mark.asyncio
    async def test_extract_no_tenant_raises(self, workflow):
        """缺少 tenant_id 时抛出 VALIDATION_ERROR"""
        state = _base_state(tenant_id=None)
        with pytest.raises(WorkflowError) as exc_info:
            await workflow._extract_node(state)
        assert exc_info.value.error_type == WorkflowErrorType.VALIDATION_ERROR

    @pytest.mark.asyncio
    async def test_extract_no_doc_type_raises(self, workflow):
        """缺少 document_type 时抛出 VALIDATION_ERROR"""
        state = _base_state(document_type="")
        with pytest.raises(WorkflowError) as exc_info:
            await workflow._extract_node(state)
        assert exc_info.value.error_type == WorkflowErrorType.VALIDATION_ERROR

    @pytest.mark.asyncio
    async def test_extract_template_not_found(self, workflow):
        """模板不存在时抛出 TEMPLATE_NOT_FOUND"""
        state = _base_state()
        with patch("agents.workflow.template_service") as mock_ts:
            mock_ts.get_template_by_code = AsyncMock(return_value=None)
            with pytest.raises(WorkflowError) as exc_info:
                await workflow._extract_node(state)
        assert exc_info.value.error_type == WorkflowErrorType.TEMPLATE_NOT_FOUND

    @pytest.mark.asyncio
    async def test_extract_llm_returns_invalid_json(self, workflow):
        """LLM 返回无效 JSON 时降级为 raw_response"""
        state = _base_state(ocr_text="一些文本")
        mock_template = {"id": "t1", "name": "检测报告", "code": "inspection_report"}

        workflow.llm.ainvoke = AsyncMock(return_value=MagicMock(
            content="这不是JSON"
        ))

        with patch("agents.workflow.template_service") as mock_ts:
            mock_ts.get_template_by_code = AsyncMock(return_value=mock_template)
            mock_ts.build_extraction_prompt.return_value = "提取以下字段..."
            result = await workflow._extract_node(state)
        # parse_llm_json 对无效 JSON 返回 {"raw_response": ...} 降级
        assert "raw_response" in result["extraction_data"]


# ============ WorkflowError ============

class TestWorkflowError:
    """WorkflowError 异常类测试"""

    def test_error_attributes(self):
        """异常属性正确设置"""
        err = WorkflowError(WorkflowErrorType.OCR_FAILED, "OCR引擎崩溃")
        assert err.error_type == WorkflowErrorType.OCR_FAILED
        assert err.message == "OCR引擎崩溃"
        assert err.step == "ocr_failed"
        assert str(err) == "OCR引擎崩溃"

    def test_custom_step(self):
        """自定义 step 覆盖默认值"""
        err = WorkflowError(WorkflowErrorType.LLM_ERROR, "超时", step="retry_3")
        assert err.step == "retry_3"

    def test_all_error_types(self):
        """所有错误类型都可正常构造"""
        for error_type in WorkflowErrorType:
            err = WorkflowError(error_type, f"测试{error_type.value}")
            assert err.error_type == error_type


# ============ result_builder ============

class TestResultBuilder:
    """结果构造器测试"""

    def test_build_error(self):
        from agents.result_builder import build_error
        result = build_error("doc-001", "处理失败")
        assert result["success"] is False
        assert result["document_id"] == "doc-001"
        assert result["error"] == "处理失败"
        assert "processing_time" not in result

    def test_build_error_with_time(self):
        from agents.result_builder import build_error
        result = build_error("doc-001", "超时", processing_time=30.5)
        assert result["processing_time"] == 30.5

    def test_build_single_success(self):
        from agents.result_builder import build_single_success
        result = build_single_success(
            document_id="doc-001",
            document_type="inspection_report",
            extraction_data={"sample_name": "LED"},
            ocr_text="短文本",
            ocr_confidence=0.95,
            processing_time=2.5,
        )
        assert result["success"] is True
        assert result["extraction_data"]["sample_name"] == "LED"
        assert result["ocr_text"] == "短文本"
        assert result["step"] == "completed"

    def test_build_single_success_truncates_long_text(self):
        from agents.result_builder import build_single_success
        long_text = "x" * 1000
        result = build_single_success(
            document_id="doc-001",
            document_type="test",
            extraction_data={},
            ocr_text=long_text,
            ocr_confidence=0.9,
            processing_time=1.0,
        )
        assert result["ocr_text"].endswith("...")
        assert len(result["ocr_text"]) == 503  # 500 + "..."

    def test_build_single_success_with_template(self):
        from agents.result_builder import build_single_success
        result = build_single_success(
            document_id="doc-001",
            document_type="test",
            extraction_data={},
            ocr_text="text",
            ocr_confidence=0.9,
            processing_time=1.0,
            template_id="t1",
            template_name="检测报告",
        )
        assert result["template_id"] == "t1"
        assert result["template_name"] == "检测报告"

    def test_build_merge_success(self):
        from agents.result_builder import build_merge_success
        result = build_merge_success(
            document_id="doc-001",
            template_id="t1",
            template_name="照明综合报告",
            document_type="lighting_combined",
            extraction_results=[{"sample_index": 0, "data": {"power": "10W"}}],
            results_a=[{"power": "10W"}],
            result_b={"distribution": "ok"},
            processing_time=5.0,
        )
        assert result["success"] is True
        assert result["sample_count"] == 1
        assert result["extraction_data"]["power"] == "10W"
        assert result["sub_results"]["result_b"]["distribution"] == "ok"
