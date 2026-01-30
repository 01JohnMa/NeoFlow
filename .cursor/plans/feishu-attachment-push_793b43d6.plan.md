---
name: feishu-attachment-push
overview: 为检测报告推送增加飞书多维表格“附件”列上传，并保持低耦合（附件为可选能力、失败不影响主流程）。
todos:
  - id: add-feishu-upload
    content: 新增飞书素材上传方法并生成附件字段
    status: completed
  - id: wire-attachment
    content: 在审核通过推送检测报告时传入文件路径
    status: completed
  - id: verify-flow
    content: 手工验证飞书记录与附件展示
    status: completed
isProject: false
---

# Feishu 附件推送改造计划

## 目标与范围

- 仅对检测报告的飞书推送增加附件列“附件”，照明/其他模板暂不处理。
- 低耦合：附件能力做成可选参数，主推送逻辑不依赖存储实现；附件上传失败不影响字段推送。

## 关键改动点

- [services/feishu_service.py](services/feishu_service.py)
- 新增飞书素材上传方法（upload media），输入本地文件路径，输出 `file_token`。
- 扩展 `push_inspection_report` 支持可选 `attachment_path`，并在字段中追加“附件”列：`{"附件": [{"file_token": "..."}]}`。
- 保持 `_push_to_table` 只负责表格写入，附件 token 的生成放在 `push_inspection_report` 中，避免耦合到表格写入通道。
- [api/routes/documents/review.py](api/routes/documents/review.py)
- 在审核通过后推送检测报告时，传入文档的本地 `file_path`。
- 若 `file_path` 缺失或文件不存在，仅推送字段不推附件。

## 低耦合策略

- 附件逻辑作为可选能力参数化，不修改 `push_by_template` 和 `push_lighting_report`。
- 附件上传失败仅记录日志，推送主字段不受影响。
- 若后续切换对象存储，只需在 `push_inspection_report` 的附件获取处替换为“获取文件流/临时文件”的实现。

## 验证方式

- 手工流程：审核通过一条检测报告，检查飞书多维表格是否写入字段并出现附件。
- 异常路径：本地文件不存在时，仍能成功推送字段并产生可读日志。

## 假设与待确认

- 当前文件来源为 `documents.file_path` 的本地路径；若你已迁移到对象存储，需要替换附件读取逻辑。
- 飞书多维表格的附件列名称固定为“附件”。