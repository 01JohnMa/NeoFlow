-- Migration 010: 为 documents 表添加自定义飞书推送文件名字段
-- 用途：用户上传文件时可指定推送到飞书的文件名，优先级高于默认的模板名+时间戳规则
-- 字段为可选（NULL 表示未设置，回退默认命名逻辑）

ALTER TABLE documents ADD COLUMN IF NOT EXISTS custom_push_name VARCHAR(255);
SELECT pg_notify('pgrst', 'reload schema');
SELECT '010: documents.custom_push_name 字段添加完成' AS message;
