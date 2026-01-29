# Test Cases: Prompt 动态构建（字段提取提示）

## Overview
- **Feature**: Prompt 动态构建（template_fields.extraction_hint 拼接）
- **Requirements Source**: 用户需求 + `services/template_service.py` 动态构建逻辑
- **Test Coverage**: 字段级提示拼接、缺省提示处理、模板示例拼接、错误场景
- **Last Updated**: 2026-01-29

## Test Case Categories

### 1. Functional Tests
测试正常流程：从数据库读取字段并拼接 extraction_hint。

#### TC-F-001: sdcm 字段提示拼接
- **Requirement**: sdcm 字段提示在 Prompt 字段行中出现
- **Priority**: High
- **Preconditions**:
  - `template_fields` 表已存在 `extraction_hint` 列
  - `sdcm` 字段 `extraction_hint` 为“仅数值，不带单位”
  - Supabase 客户端已初始化
- **Test Steps**:
  1. 调用 `template_service.get_template_by_code(tenant_id, "integrating_sphere")`
  2. 调用 `template_service.build_extraction_prompt(template, ocr_text)`
  3. 在 prompt 中定位 `sdcm` 行
- **Expected Results**:
  - prompt 行包含 `| 色容差SDCM | sdcm | 仅数值，不带单位`
- **Postconditions**: 无

#### TC-F-002: 其他字段无提示时仍可生成
- **Requirement**: 未配置 extraction_hint 的字段仍能生成行
- **Priority**: Medium
- **Preconditions**:
  - 存在至少一个 `extraction_hint` 为空的字段
- **Test Steps**:
  1. 获取模板
  2. 构建 prompt
  3. 查找该字段行
- **Expected Results**:
  - 字段行存在
  - 说明列不报错，允许为空或仅包含类型提示
- **Postconditions**: 无

#### TC-F-003: 字段类型提示与 extraction_hint 合并
- **Requirement**: `field_type=number/date` 的类型提示与 extraction_hint 同时出现
- **Priority**: Medium
- **Preconditions**:
  - 存在 `field_type=number` 且有 `extraction_hint` 的字段
- **Test Steps**:
  1. 构建 prompt
  2. 查找该字段行
- **Expected Results**:
  - 行中同时包含类型提示（如“（数值类型）”）和 extraction_hint
- **Postconditions**: 无

### 2. Edge Case Tests
边界与缺省情况。

#### TC-E-001: extraction_hint 为空字符串
- **Requirement**: 空提示不影响格式
- **Priority**: Low
- **Preconditions**:
  - `extraction_hint` 为 `""`
- **Test Steps**:
  1. 构建 prompt
  2. 检查该字段行
- **Expected Results**:
  - 行生成成功，不出现多余空格或异常字符
- **Postconditions**: 无

#### TC-E-002: extraction_hint 为 None/NULL
- **Requirement**: None/NULL 正常处理
- **Priority**: Low
- **Preconditions**:
  - `extraction_hint` 为 NULL
- **Test Steps**:
  1. 构建 prompt
  2. 检查该字段行
- **Expected Results**:
  - 行生成成功，不抛异常
- **Postconditions**: 无

### 3. Error Handling Tests
错误与依赖缺失场景。

#### TC-ERR-001: Supabase 未初始化
- **Requirement**: 未初始化时提示清晰错误
- **Priority**: High
- **Preconditions**:
  - 未调用 `supabase_service.initialize()`
- **Test Steps**:
  1. 调用 `get_template_by_code`
- **Expected Results**:
  - 抛出 `Supabase未初始化，请先调用initialize()` 错误
- **Postconditions**: 无

#### TC-ERR-002: 模板不存在
- **Requirement**: 模板不存在返回 None
- **Priority**: Medium
- **Preconditions**:
  - 使用不存在的 `template_code`
- **Test Steps**:
  1. 调用 `get_template_by_code(tenant_id, "not_exist")`
- **Expected Results**:
  - 返回 None，并记录日志
- **Postconditions**: 无

### 4. State Transition Tests
本功能无状态机，不适用。

## Test Coverage Matrix

| Requirement ID | Test Cases | Coverage Status |
|---------------|------------|-----------------|
| REQ-001: 字段级提示拼接 | TC-F-001, TC-F-003 | ✓ Complete |
| REQ-002: 缺省提示处理 | TC-F-002, TC-E-001, TC-E-002 | ✓ Complete |
| REQ-003: 依赖错误处理 | TC-ERR-001, TC-ERR-002 | ✓ Complete |

## Notes
- 若将测试与数据库强依赖，需确保本地 Supabase 容器已启动且 schema 已迁移。
- `sdcm` 字段示例依赖 `template_fields` 中实际记录，必要时可手动确认该字段存在。
