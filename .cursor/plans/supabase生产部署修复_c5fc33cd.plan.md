---
name: Supabase生产部署修复
overview: 将所有迁移脚本合并为单一初始化文件，实现数据库启动时完全自动初始化，无需手动执行 SQL。
todos:
  - id: create-merged-init
    content: 创建合并后的 000_init.sql 包含所有初始化内容
    status: completed
  - id: cleanup-old-files
    content: 删除旧的分散迁移文件
    status: completed
  - id: update-readme
    content: 更新 README.md 简化部署说明
    status: completed
---

