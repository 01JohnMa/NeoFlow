---
name: backend-refactor
overview: 后端代码重构优化，提升代码质量和可维护性
todos:
  - id: batch-1
    content: OCR 结果验证
    status: pending
  - id: batch-2
    content: 工作流错误格式统一
    status: pending
  - id: batch-3
    content: 添加 LLM/飞书重试机制
    status: pending
  - id: batch-4
    content: SupabaseService 方法去重（save + get）
    status: pending
  - id: batch-5
    content: 后台任务去重
    status: pending
  - id: batch-6
    content: 文档类型常量提取
    status: pending
isProject: false
---

# 后端重构优化计划

## 目标

对后端代码进行重构优化，提升代码质量和可维护性，**确保不影响现有功能**。

## 重构项目清单

### 1. SupabaseService 重复代码提取（扩展版）

**文件**: [services/supabase_service.py](services/supabase_service.py)

**问题**: 4个保存方法 + 4个获取方法代码高度重复

**Save 方法**:

- `save_inspection_report()` (行354-369)
- `save_express()` (行382-396)
- `save_sampling_form()` (行409-423)
- `save_lighting_report()` (行436-452)

**Get 方法**:

- `get_inspection_report()` (行371-378)
- `get_express()` (行398-405)
- `get_sampling_form()` (行425-432)
- `get_lighting_report()` (行454-461)

**计划**:

- 提取通用方法 `_save_to_table(table_name, document_id, data, normalize_func=None)`
- 提取通用方法 `_get_from_table(table_name, document_id)`
- 保留原有8个方法作为薄包装（向后兼容）
- 保留 `_normalize_lighting_units()` 特殊处理

**修改行数**: ~70行

---

### 2. 后台任务代码去重

**文件**: [api/routes/documents/process.py](api/routes/documents/process.py)

**问题**:

- `process_document_task()` (行158-228)
- `process_document_with_template_task()` (行341-394)

**计划**:

- 提取 `_save_processing_result()` - 统一保存提取结果
- 提取 `_handle_success_result()` - 统一处理成功逻辑
- 提取 `_handle_failure_result()` - 统一处理失败逻辑
- 保留原有函数签名（向后兼容）

**修改行数**: ~50行

---

### 3. ~~配置类型优化~~ (已移除)

**原因**: 当前使用 `@property` 解析字符串列表是 pydantic-settings 处理环境变量的最佳实践。`.env` 文件只支持字符串类型，改用 `List[str]` 会增加复杂度无明显收益。

---

### 4. 添加 LLM/飞书重试机制

**文件**:

- [services/feishu_service.py](services/feishu_service.py)
- [agents/workflow.py](agents/workflow.py)

**计划**:

- 使用 `tenacity` 库添加重试装饰器
- LLM 调用：3次重试，指数退避，仅重试网络/超时异常
- 飞书推送：3次重试，指数退避，排除权限错误（不可重试）

**修改行数**: ~40行

---

### 5. 统一工作流错误格式

**文件**: [agents/workflow.py](agents/workflow.py)

**问题**: 节点失败返回格式不统一

**计划**:

- 添加 `_make_error_response()` 辅助方法
- 统一所有节点错误返回格式
- 添加错误类型枚举

**修改行数**: ~25行

---

### 6. 添加 OCR 结果验证

**文件**: [services/ocr_service.py](services/ocr_service.py)

**计划**:

- 添加 `_validate_ocr_result()` 方法
- 验证返回数据完整性
- 添加置信度阈值配置 `OCR_MIN_CONFIDENCE`

**修改行数**: ~20行

---

### 7. 文档类型常量提取（新增）

**文件**: 新建 `constants/document_types.py`

**问题**: 文档类型字符串在多处硬编码

**计划**:

```python
class DocumentTypeTable:
    """文档类型与表名映射"""
    INSPECTION_REPORT = "inspection_reports"
    EXPRESS = "expresses"
    SAMPLING_FORM = "sampling_forms"
    LIGHTING_REPORT = "lighting_reports"

# 类型到表名的映射
DOC_TYPE_TABLE_MAP = {
    "检验报告": DocumentTypeTable.INSPECTION_REPORT,
    "快递单": DocumentTypeTable.EXPRESS,
    "抽样单": DocumentTypeTable.SAMPLING_FORM,
    "照明综合": DocumentTypeTable.LIGHTING_REPORT,
}
```

**修改行数**: ~30行

---

## 实施顺序（分批进行）

| 批次 | 重构项 | 影响范围 | 风险 |

|------|--------|----------|------|

| 批次1 | OCR 结果验证 | ocr_service.py | 低 |

| 批次2 | 工作流错误格式 | workflow.py | 低 |

| 批次3 | 添加重试机制 | feishu_service.py, workflow.py | 中 |

| 批次4 | Supabase 方法去重 | supabase_service.py | 中 |

| 批次5 | 后台任务去重 | process.py | 中 |

| 批次6 | 文档类型常量提取 | 多文件 | 低 |

每批次完成并验证通过后，再进行下一批次。

---

## 重试机制详情

对以下操作添加 3 次重试 + 指数退避：

**LLM 调用** (`agents/workflow.py`):

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    reraise=True
)
async def _llm_invoke_with_retry(self, messages):
    ...
```

**飞书推送** (`services/feishu_service.py`):

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

def _is_retryable_error(exception):
    """判断是否为可重试错误（排除权限错误）"""
    if isinstance(exception, FeishuAPIError):
        # 权限错误、配置错误不重试
        return exception.code not in [99991663, 1254043, 1254060]
    return isinstance(exception, (httpx.TimeoutException, httpx.NetworkError))

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception(_is_retryable_error),
    reraise=True
)
async def _push_to_table_with_retry(self, ...):
    ...
```

---

## 验证计划

每批次完成后进行：

### 静态检查

```bash
python -m py_compile services/supabase_service.py
python -m py_compile services/ocr_service.py
python -m py_compile services/feishu_service.py
python -m py_compile agents/workflow.py
python -m py_compile api/routes/documents/process.py
```

### 类型检查（可选）

```bash
python -m mypy services/supabase_service.py --ignore-missing-imports
```

### 功能测试

```bash
# 1. 健康检查
curl http://localhost:8080/api/health

# 2. API 文档可访问
curl http://localhost:8080/docs

# 3. 单元测试（如有）
pytest tests/ -v

# 4. 测试文档上传处理（可选，需要真实测试文件）
```

### 批次验证标准

- [ ] 语法检查通过
- [ ] 模块导入无错误
- [ ] API 健康检查返回 200
- [ ] 原有功能不受影响
- [ ] 重构方法行为与原方法一致

---

## 回滚计划

- 每个批次使用独立 git commit
- 保留原有函数作为薄包装确保向后兼容
- 发现问题可快速回滚：
```bash
git revert <commit_hash>
```


---

## 预计工作量

| 批次 | 重构项 | 修改行数 |

|------|--------|----------|

| 批次1 | OCR 结果验证 | ~20行 |

| 批次2 | 工作流错误格式 | ~25行 |

| 批次3 | 添加重试机制 | ~40行 |

| 批次4 | Supabase 方法去重 | ~70行 |

| 批次5 | 后台任务去重 | ~50行 |

| 批次6 | 文档类型常量提取 | ~30行 |

| **总计** | | **~235行** |