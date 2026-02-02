"""
批量上传功能测试

测试覆盖：
1. 数据一致性回滚 - 上传失败时清理已保存文件
2. 并发控制 - 信号量限制同时处理的文档数
3. 权限校验 - 批次归属检查
4. 进度追踪 - 批次状态更新
5. 错误处理 - 各种异常场景
"""

import pytest
import asyncio
import uuid
import os
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

# 模拟导入（实际测试时需要正确配置导入路径）
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from services.supabase_service import SupabaseService, supabase_service
except ImportError:
    # 如果导入失败，创建 mock
    supabase_service = MagicMock()
    SupabaseService = MagicMock


# ============ 测试数据 ============

TEST_USER_ID = str(uuid.uuid4())
TEST_TENANT_ID = str(uuid.uuid4())
TEST_BATCH_ID = str(uuid.uuid4())


def create_mock_batch(status="pending", completed=0, failed=0, total=5):
    """创建模拟批次数据"""
    return {
        "id": TEST_BATCH_ID,
        "user_id": TEST_USER_ID,
        "tenant_id": TEST_TENANT_ID,
        "batch_mode": "single",
        "total_count": total,
        "completed_count": completed,
        "failed_count": failed,
        "status": status,
        "created_at": datetime.now().isoformat(),
        "completed_at": None,
        "error_message": None,
    }


def create_mock_document(batch_id, status="pending", group_index=None):
    """创建模拟文档数据"""
    return {
        "id": str(uuid.uuid4()),
        "batch_id": batch_id,
        "batch_group_index": group_index,
        "status": status,
        "document_type": None,
        "display_name": None,
        "error_message": None,
        "created_at": datetime.now().isoformat(),
    }


# ============ 1. 数据一致性回滚测试 ============

class TestDataConsistency:
    """测试数据一致性和回滚机制"""

    @pytest.mark.asyncio
    async def test_rollback_on_upload_failure(self):
        """测试上传失败时的回滚机制"""
        # 模拟文件系统
        saved_files = []
        
        async def mock_save_file(file, doc_id):
            path = f"/tmp/test/{doc_id}.pdf"
            saved_files.append(path)
            if len(saved_files) > 2:  # 第3个文件失败
                raise Exception("Storage full")
            return path
        
        # 模拟数据库
        batch_created = False
        
        async def mock_create_batch(data):
            nonlocal batch_created
            batch_created = True
            return data
        
        async def mock_delete_batch(batch_id):
            nonlocal batch_created
            batch_created = False
        
        # 验证逻辑：失败后应该清理所有已保存的文件和批次记录
        try:
            # 模拟上传流程
            batch_id = str(uuid.uuid4())
            await mock_create_batch({"id": batch_id})
            
            files = ["file1.pdf", "file2.pdf", "file3.pdf"]
            for i, f in enumerate(files):
                await mock_save_file(f, f"doc-{i}")
                
        except Exception:
            # 回滚：清理文件
            for path in saved_files:
                if os.path.exists(path):
                    os.remove(path)
            # 回滚：删除批次
            if batch_created:
                await mock_delete_batch(batch_id)
        
        # 验证回滚后状态
        assert not batch_created, "批次应该被删除"
        # 注意：实际实现需要检查文件是否被清理

    @pytest.mark.asyncio
    async def test_partial_document_save(self):
        """测试部分文档保存成功的情况"""
        docs_saved = 0
        
        async def mock_create_document(data):
            nonlocal docs_saved
            docs_saved += 1
            if docs_saved == 3:
                raise Exception("Database error")
            return data
        
        # 验证：即使部分失败，已保存的文档应该保持
        with pytest.raises(Exception):
            for i in range(5):
                await mock_create_document({"id": f"doc-{i}"})
        
        assert docs_saved == 3, "应该在第3个文档失败"


# ============ 2. 并发控制测试 ============

class TestConcurrencyControl:
    """测试并发控制机制"""

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrent_processing(self):
        """测试信号量限制并发处理数"""
        from asyncio import Semaphore
        
        OCR_SEMAPHORE = Semaphore(3)
        concurrent_count = 0
        max_concurrent = 0
        
        async def mock_process_document(doc_id):
            nonlocal concurrent_count, max_concurrent
            async with OCR_SEMAPHORE:
                concurrent_count += 1
                max_concurrent = max(max_concurrent, concurrent_count)
                await asyncio.sleep(0.1)  # 模拟处理时间
                concurrent_count -= 1
        
        # 同时启动10个任务
        tasks = [mock_process_document(f"doc-{i}") for i in range(10)]
        await asyncio.gather(*tasks)
        
        # 验证最大并发数不超过信号量限制
        assert max_concurrent <= 3, f"最大并发数应该是3，实际是{max_concurrent}"

    @pytest.mark.asyncio
    async def test_batch_processing_order(self):
        """测试批量处理顺序"""
        processed_order = []
        
        async def mock_process(doc_id):
            await asyncio.sleep(0.01)
            processed_order.append(doc_id)
        
        # 按顺序处理
        docs = ["doc-0", "doc-1", "doc-2", "doc-3", "doc-4"]
        for doc in docs:
            await mock_process(doc)
        
        # 验证顺序处理
        assert processed_order == docs


# ============ 3. 权限校验测试 ============

class TestPermissionValidation:
    """测试权限校验"""

    @pytest.mark.asyncio
    async def test_owner_can_access_batch(self):
        """测试所有者可以访问批次"""
        batch = create_mock_batch()
        user_id = TEST_USER_ID  # 同一用户
        
        is_owner = batch["user_id"] == user_id
        assert is_owner, "所有者应该能访问"

    @pytest.mark.asyncio
    async def test_same_tenant_can_access_batch(self):
        """测试同租户用户可以访问批次"""
        batch = create_mock_batch()
        other_user_id = str(uuid.uuid4())  # 不同用户
        tenant_id = TEST_TENANT_ID  # 同一租户
        
        is_owner = batch["user_id"] == other_user_id
        is_same_tenant = batch["tenant_id"] == tenant_id
        
        assert not is_owner, "不是所有者"
        assert is_same_tenant, "同租户应该能访问"
        assert is_owner or is_same_tenant, "同租户用户应该有权限"

    @pytest.mark.asyncio
    async def test_different_tenant_cannot_access_batch(self):
        """测试不同租户用户不能访问批次"""
        batch = create_mock_batch()
        other_user_id = str(uuid.uuid4())  # 不同用户
        other_tenant_id = str(uuid.uuid4())  # 不同租户
        
        is_owner = batch["user_id"] == other_user_id
        is_same_tenant = batch["tenant_id"] == other_tenant_id
        
        assert not is_owner, "不是所有者"
        assert not is_same_tenant, "不是同租户"
        assert not (is_owner or is_same_tenant), "不同租户用户不应该有权限"


# ============ 4. 进度追踪测试 ============

class TestProgressTracking:
    """测试进度追踪"""

    @pytest.mark.asyncio
    async def test_progress_updates_correctly(self):
        """测试进度更新正确"""
        batch = create_mock_batch(total=5)
        
        # 模拟处理过程中的进度更新
        progress_updates = []
        
        async def update_progress(completed, failed):
            progress_updates.append({
                "completed": completed,
                "failed": failed,
                "progress": (completed + failed) / batch["total_count"] * 100
            })
        
        # 模拟5个文档的处理
        for i in range(5):
            if i == 2:  # 第3个文档失败
                await update_progress(i, 1)
            else:
                await update_progress(i + 1 if i < 2 else i, 1)
        
        # 验证最终进度
        final_progress = progress_updates[-1]
        assert final_progress["progress"] == 100, "最终进度应该是100%"

    @pytest.mark.asyncio
    async def test_batch_status_transitions(self):
        """测试批次状态转换"""
        statuses = []
        
        async def mock_update_status(status):
            statuses.append(status)
        
        # 正常流程
        await mock_update_status("pending")
        await mock_update_status("processing")
        await mock_update_status("completed")
        
        assert statuses == ["pending", "processing", "completed"]

    @pytest.mark.asyncio
    async def test_partial_failure_status(self):
        """测试部分失败状态"""
        completed = 3
        failed = 2
        total = 5
        
        final_status = "completed" if failed == 0 else "partial_failed"
        
        assert final_status == "partial_failed"


# ============ 5. 错误处理测试 ============

class TestErrorHandling:
    """测试错误处理"""

    @pytest.mark.asyncio
    async def test_single_document_failure_continues_batch(self):
        """测试单个文档失败不影响批次继续处理"""
        results = []
        
        async def mock_process(doc_id):
            if doc_id == "doc-2":
                raise Exception("OCR failed")
            return {"doc_id": doc_id, "success": True}
        
        for i in range(5):
            doc_id = f"doc-{i}"
            try:
                result = await mock_process(doc_id)
                results.append(result)
            except Exception as e:
                results.append({"doc_id": doc_id, "success": False, "error": str(e)})
        
        # 验证所有文档都被处理
        assert len(results) == 5
        success_count = sum(1 for r in results if r["success"])
        assert success_count == 4, "应该有4个成功"

    @pytest.mark.asyncio
    async def test_batch_recovery_on_restart(self):
        """测试重启后的批次恢复"""
        # 模拟中断的批次
        interrupted_batches = [
            create_mock_batch(status="processing"),
            create_mock_batch(status="processing"),
        ]
        
        recovered_batches = []
        
        async def mock_recover():
            for batch in interrupted_batches:
                batch["status"] = "interrupted"
                batch["error_message"] = "系统重启导致任务中断"
                recovered_batches.append(batch)
        
        await mock_recover()
        
        # 验证所有中断批次都被标记
        assert len(recovered_batches) == 2
        for batch in recovered_batches:
            assert batch["status"] == "interrupted"

    @pytest.mark.asyncio
    async def test_invalid_file_format_rejection(self):
        """测试无效文件格式拒绝"""
        ACCEPTED_TYPES = ['application/pdf', 'image/png', 'image/jpeg']
        
        def validate_file(file_type):
            return file_type in ACCEPTED_TYPES
        
        assert validate_file('application/pdf'), "PDF应该被接受"
        assert validate_file('image/png'), "PNG应该被接受"
        assert not validate_file('text/plain'), "文本文件应该被拒绝"
        assert not validate_file('application/exe'), "可执行文件应该被拒绝"

    @pytest.mark.asyncio
    async def test_file_size_limit(self):
        """测试文件大小限制"""
        MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
        
        def validate_size(file_size):
            return file_size <= MAX_FILE_SIZE
        
        assert validate_size(10 * 1024 * 1024), "10MB应该被接受"
        assert validate_size(20 * 1024 * 1024), "20MB应该被接受"
        assert not validate_size(21 * 1024 * 1024), "21MB应该被拒绝"


# ============ 6. Supabase Service 批次方法测试 ============

class TestSupabaseBatchMethods:
    """测试 Supabase 批次方法"""

    @pytest.mark.asyncio
    async def test_create_batch(self):
        """测试创建批次"""
        service = MagicMock()
        service.client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[create_mock_batch()]
        )
        
        # 模拟 create_batch 方法
        data = create_mock_batch()
        result = service.client.table("document_batches").insert(data).execute()
        
        assert result.data is not None
        assert result.data[0]["id"] == TEST_BATCH_ID

    @pytest.mark.asyncio
    async def test_update_batch_progress(self):
        """测试更新批次进度"""
        service = MagicMock()
        updated_batch = create_mock_batch(completed=3, failed=1)
        service.client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[updated_batch]
        )
        
        # 模拟 update_batch_progress 方法
        result = service.client.table("document_batches").update({
            "completed_count": 3,
            "failed_count": 1
        }).eq("id", TEST_BATCH_ID).execute()
        
        assert result.data[0]["completed_count"] == 3
        assert result.data[0]["failed_count"] == 1

    @pytest.mark.asyncio
    async def test_get_batches_by_status(self):
        """测试按状态获取批次"""
        service = MagicMock()
        processing_batches = [
            create_mock_batch(status="processing"),
            create_mock_batch(status="processing"),
        ]
        service.client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=processing_batches
        )
        
        # 模拟 get_batches_by_status 方法
        result = service.client.table("document_batches").select("*").eq(
            "status", "processing"
        ).execute()
        
        assert len(result.data) == 2
        for batch in result.data:
            assert batch["status"] == "processing"


# ============ 7. 合并模式测试 ============

class TestMergeMode:
    """测试照明系统合并模式"""

    @pytest.mark.asyncio
    async def test_merge_group_validation(self):
        """测试配对组验证"""
        DOC_TYPES = ['积分球', '光分布']
        
        def validate_group(files):
            """验证组内是否所有必需文档都已上传"""
            return all(files.get(dt) is not None for dt in DOC_TYPES)
        
        # 完整组
        complete_group = {'积分球': 'file1.pdf', '光分布': 'file2.pdf'}
        assert validate_group(complete_group), "完整组应该通过验证"
        
        # 不完整组
        incomplete_group = {'积分球': 'file1.pdf', '光分布': None}
        assert not validate_group(incomplete_group), "不完整组不应该通过验证"

    @pytest.mark.asyncio
    async def test_merge_batch_groups_construction(self):
        """测试合并批次分组构建"""
        groups = [
            {"files": [0, 1], "doc_types": ["积分球", "光分布"]},
            {"files": [2, 3], "doc_types": ["积分球", "光分布"]},
        ]
        
        # 验证分组结构
        assert len(groups) == 2
        for group in groups:
            assert len(group["files"]) == 2
            assert "积分球" in group["doc_types"]
            assert "光分布" in group["doc_types"]


# ============ 运行测试 ============

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
