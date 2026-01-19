# Supabase 本地部署指南

## 目录结构

```
supabase/
├── docker-compose.yml                      # Docker 服务编排
├── kong.yml                                # API 网关配置
├── migrations/                             # 数据库初始化脚本
│   ├── 000_init.sql                       # 完整初始化（自动执行）
│   ├── upgrade_001_add_display_name.sql   # 增量迁移（仅升级用）
│   └── upgrade_002_remove_triggers.sql    # 增量迁移（仅升级用）
├── volumes/                                # Docker 数据卷（gitignore）
│   ├── db/data/                           # PostgreSQL 数据
│   └── storage/                           # Storage 文件
└── README.md
```

## 部署步骤

### 1. 首次部署（一条命令）

```bash
# 启动所有服务，数据库初始化自动完成
docker-compose up -d
```

`000_init.sql` 会在数据库容器首次启动时自动执行，包含：
- 角色和 Schema 初始化
- Storage 基础表和 RLS 策略
- OCR 应用表和索引
- 用户数据隔离 RLS 策略
- 管理员权限策略

### 2. 重建数据库（测试环境）

```bash
# 1. 停止所有容器
docker-compose down

# 2. 删除数据库数据（Windows 用 rd /s /q）
rm -rf ./volumes/db/data

# 3. 重新启动
docker-compose up -d
```

### 3. 现有部署升级

如果从旧版本升级，需要手动执行增量迁移：

```bash
# 添加 display_name 字段
docker exec -i supabase-db psql -U postgres -d postgres -f /docker-entrypoint-initdb.d/upgrade_001_add_display_name.sql

# 移除旧触发器
docker exec -i supabase-db psql -U postgres -d postgres -f /docker-entrypoint-initdb.d/upgrade_002_remove_triggers.sql
```

## 常见问题

### Q1: auth 容器报错 "schema auth does not exist"
**原因**: Schema 创建顺序错误  
**解决**: 已在 `000_init.sql` 中修复，确保先 `CREATE SCHEMA` 再 `GRANT`

### Q2: storage 容器不断重启 "relation storage.objects does not exist"
**原因**: storage-api 需要预先存在的基础表  
**解决**: 已在 `000_init.sql` 中包含 Storage 表创建

### Q3: 创建扩展报错 "permission denied for function pg_read_file"
**原因**: Supabase postgres 镜像对 `CREATE EXTENSION` 有特殊触发器  
**解决**: 使用 PostgreSQL 原生的 `gen_random_uuid()`，不需要 `uuid-ossp` 扩展

### Q4: Studio 看不到 auth.users 表
**原因**: `supabase_admin` 用户对 auth 服务创建的表没有权限  
**解决**: 已在 `000_init.sql` 中通过 `ALTER DEFAULT PRIVILEGES` 预设权限  
**备用修复**: 如果仍有问题，执行：
```bash
docker exec -i supabase-db psql -U postgres -d postgres -c "GRANT ALL ON ALL TABLES IN SCHEMA auth TO supabase_admin; GRANT ALL ON ALL SEQUENCES IN SCHEMA auth TO supabase_admin; GRANT USAGE ON SCHEMA auth TO supabase_admin;"
```

### Q5: 生产环境密码安全
**警告**: `000_init.sql` 中的密码 `123456` 仅供开发测试  
**解决**: 生产部署前必须修改为强密码，建议使用 `openssl rand -base64 32` 生成

## Migration 文件说明

| 文件 | 作用 | 执行方式 |
|------|------|----------|
| 000_init.sql | 完整初始化（角色、表、RLS） | ✅ 容器启动时自动执行 |
| upgrade_001_add_display_name.sql | 添加 display_name 字段 | ❌ 仅旧版本升级时手动执行 |
| upgrade_002_remove_triggers.sql | 移除旧状态触发器 | ❌ 仅旧版本升级时手动执行 |

## 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| Kong (API Gateway) | 8000 | 主入口 |
| Studio | 3001 | 管理界面 |
| PostgreSQL | 5432 | 数据库 |
| Auth | 9999 | 认证服务 |
| REST | 3002 | REST API |
| Storage | 5000 | 文件存储 |

## 文档状态说明

| 状态 | 说明 |
|------|------|
| pending | 待处理 |
| uploaded | 已上传 |
| processing | OCR 处理中 |
| pending_review | 待人工审核 |
| completed | 已完成（审核通过）|
| failed | 处理失败 |

## 设置管理员用户

auth 服务启动后，可通过 SQL 设置管理员：

```sql
UPDATE auth.users 
SET raw_app_meta_data = jsonb_set(
    COALESCE(raw_app_meta_data, '{}'::jsonb), 
    '{is_admin}', 
    'true'
) 
WHERE email = 'admin@example.com';
```
