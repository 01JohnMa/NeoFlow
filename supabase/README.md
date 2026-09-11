# Supabase 本地部署指南

## 目录结构

```
supabase/
├── docker-compose.yml      # Docker 服务编排（db/auth/rest/migrations）
├── initdb/                 # 仅 db 容器首次初始化执行
│   └── 000_bootstrap.sh    # 执行 000_init.sql + 从环境变量设置角色密码
├── migrations/             # 迁移脚本
│   ├── 000_init.sql        # 基础结构（bootstrap 与迁移器都会执行，幂等）
│   ├── 001~020_*.sql       # 增量迁移（migrations 服务应用并记录）
│   └── run_migrations.sh   # 迁移执行器脚本
├── volumes/                # Docker 数据卷（gitignore）
│   └── db/data/            # PostgreSQL 数据
└── README.md
```

## 部署步骤

### 1. 首次部署（一条命令）

```bash
# 启动所有服务，数据库初始化自动完成
docker-compose up -d
```

说明：
- 首次初始化由 `initdb/000_bootstrap.sh` 执行：应用 `migrations/000_init.sql`，
  并用 `POSTGRES_PASSWORD` 设置数据库角色密码。
- 增量迁移由 `migrations` 服务在 db/auth 就绪后自动处理
  （见 `migrations/run_migrations.sh`，只处理 `*.sql`）。
- 只有 `initdb/` 挂载到 `docker-entrypoint-initdb.d`，避免依赖 auth 服务的
  迁移在 auth 启动前执行导致初始化失败。

`000_init.sql` 会在数据库容器首次启动时自动执行，包含：
- 角色和 Schema 初始化
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

### Q2: 创建扩展报错 "permission denied for function pg_read_file"
**原因**: Supabase postgres 镜像对 `CREATE EXTENSION` 有特殊触发器  
**解决**: 使用 PostgreSQL 原生的 `gen_random_uuid()`，不需要 `uuid-ossp` 扩展

### Q3: 数据库角色密码从哪里来
**说明**: `000_init.sql` 不包含任何硬编码密码。首次初始化时由
`initdb/000_bootstrap.sh` 读取 `POSTGRES_PASSWORD` 环境变量，
统一设置 `supabase_auth_admin`、`supabase_storage_admin`、`authenticator`、
`supabase_admin` 的密码，与 compose 中 auth/rest 的连接串保持一致。  
**已部署数据库**: `initdb/` 仅在数据目录为空时执行，现有角色密码保持不变；
如需轮换，手动执行 `ALTER ROLE ... PASSWORD`。

## Migration 文件说明

| 文件 | 作用 | 执行方式 |
|------|------|----------|
| 000_init.sql | 完整初始化（角色、表、RLS） | ✅ 首次由 initdb 执行，迁移器幂等重放并记录 |
| 001_multi_tenant.sql | 多租户基础表与策略 | ✅ 迁移执行器自动执行 |
| 002~020_*.sql | 历史增量迁移（认证、CRM、Excel 输出、安全加固等） | ✅ 迁移执行器自动执行 |
| 021_configurations.sql | Configuration/Revision 领域表与旧模板数据迁移 | ✅ 迁移执行器自动执行 |
| 022_results_and_job_revision.sql | Result 存储与 Job 固定 Revision | ✅ 迁移执行器自动执行 |
| 023_drop_legacy_business_tables.sql | 删除旧业务结果表、动态 DDL 与旧模板表 | ✅ 迁移执行器自动执行（幂等） |
| run_migrations.sh | 迁移执行器脚本 | ✅ 容器启动时自动运行 |

## 配置与结果存储

- 抽取配置以 **Configuration + 不可变 Revision** 存储，definition 为 JSONB，不再对业务表执行动态 DDL（`schema_sync` 已随 023 删除）。
- 抽取/解析结果统一写入 **Result**（JSONB），飞书与 Excel 输出从 Result 读取。
- 旧业务结果表与旧模板表由 `023_drop_legacy_business_tables.sql` 删除，仓库中不再有表名映射或镜像写入。

## 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| PostgreSQL | 5432 | 数据库（宿主机映射） |
| Auth | 9999 | 认证服务（宿主机映射） |
| REST | 3002 | PostgREST（宿主机映射，容器内为 3000） |

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
