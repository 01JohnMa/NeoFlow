# Batch Layout Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 重构批处理上传页面布局，将推送文件名统一移动到右侧侧栏，并删除任务摘要和多余说明文案，保留必要的错误反馈与处理进度。

**Architecture:** 保持现有批处理数据结构和提交逻辑不变，只调整 React 组件职责分层。`CompositeGroupEditor` 专注分组上传编辑，`CompositeUploadPanel` 负责整体布局和右侧命名侧栏。通过先写组件测试再改实现，确保结构调整不破坏既有交互。

**Tech Stack:** React 18, TypeScript, Vite, Vitest, Tailwind CSS

---

### Task 1: 为批处理布局调整补充失败测试

**Files:**
- Modify: `web/src/features/composite-upload/core/compositeUpload.test.ts`
- Create: `web/src/features/composite-upload/CompositeUploadPanel.test.tsx`

**Step 1: 写一个新的组件测试文件，构造最小场景和分组数据**

```tsx
import { describe, expect, it } from 'vitest'

it('将推送文件名输入放到统一侧栏并隐藏任务摘要', () => {
  expect(true).toBe(false)
})
```

**Step 2: 让测试断言这些新结构**
- 页面存在分组上传区
- 页面存在按“分组 1 / 分组 2”组织的命名区
- 不再显示“任务摘要”
- 不再显示“当前组自定义文件名”与“实际生效名称”

**Step 3: 运行单测验证失败**

Run: `npm test -- src/features/composite-upload/CompositeUploadPanel.test.tsx`

Expected: FAIL，因为新测试文件或断言对应的结构还不存在。

---

### Task 2: 收缩 `CompositeGroupEditor`，移除组内命名模块和顶部说明

**Files:**
- Modify: `web/src/features/composite-upload/components/CompositeGroupEditor.tsx`
- Test: `web/src/features/composite-upload/CompositeUploadPanel.test.tsx`

**Step 1: 删除顶部说明区域**
移除“组合分组”标题和说明段。

**Step 2: 删除每组卡片中的命名模块**
移除：
- “当前组自定义文件名”标签
- 推荐名按钮所在的组内容器
- 输入框
- “实际生效名称”文案

**Step 3: 同步收紧组件 props**
如果某些 props 不再由 `CompositeGroupEditor` 使用，就从组件签名中删除，并调整调用方。

**Step 4: 运行测试**

Run: `npm test -- src/features/composite-upload/CompositeUploadPanel.test.tsx`

Expected: 仍可能 FAIL，因为右侧侧栏尚未实现。

---

### Task 3: 在 `CompositeUploadPanel` 实现左右布局和统一命名侧栏

**Files:**
- Modify: `web/src/features/composite-upload/CompositeUploadPanel.tsx`
- Test: `web/src/features/composite-upload/CompositeUploadPanel.test.tsx`

**Step 1: 将主体改为响应式两栏布局**
桌面端使用左右分栏，小屏堆叠。

**Step 2: 在右侧新增命名侧栏卡片**
按组渲染：
- 分组编号
- 推送文件名输入框
- 推荐文件名按钮
- placeholder 使用 `groupEffectivePushNames[group.id]`

**Step 3: 删除 `任务摘要` 模块**
完整移除统计块，不再显示完整组/部分组/空组等信息。

**Step 4: 保留原有错误与提交区**
确保以下内容不丢失：
- 全局错误
- 上传错误
- 提交按钮
- 处理中进度条

**Step 5: 运行测试验证通过**

Run: `npm test -- src/features/composite-upload/CompositeUploadPanel.test.tsx`

Expected: PASS

---

### Task 4: 运行类型检查与相关测试，确认改造未引入回归

**Files:**
- Verify only

**Step 1: 运行新增组件测试**

Run: `npm test -- src/features/composite-upload/CompositeUploadPanel.test.tsx`

Expected: PASS

**Step 2: 运行已有核心测试**

Run: `npm test -- src/features/composite-upload/core/compositeUpload.test.ts`

Expected: PASS

**Step 3: 运行 lint 检查前端改动文件**

Run: `npm run lint -- src/features/composite-upload/CompositeUploadPanel.tsx src/features/composite-upload/components/CompositeGroupEditor.tsx src/features/composite-upload/CompositeUploadPanel.test.tsx`

Expected: PASS 或只出现与本次无关的已知告警

**Step 4: 如 lint 命令不支持文件参数，则改用全量 lint 或使用编辑器诊断核对改动文件**

---

### Task 5: 记录结果并准备收尾

**Files:**
- Modify: `docs/plans/2026-03-24-batch-layout-cleanup-design.md`（如需补充实现备注）

**Step 1: 记录实际落地与设计差异（如果有）**

**Step 2: 汇总验证结果并准备交付说明**

---
