# Supabase Cloud 部署说明

自建（`supabase/docker-compose.yml`）与云项目（Supabase Cloud）的迁移集不同：
云项目已有角色、schema 与 storage 管理，且旧业务/模板链已被 #12 删除。
本目录提供云项目专用的补充脚本，其余复用 `../migrations/` 的正式迁移。

## 应用顺序

| # | 文件 | 说明 |
|---|------|------|
| 1 | `cloud/000_cloud_base.sql` | 从 `000_init.sql` 摘出的 `documents` / `processing_logs`（跳过自建 bootstrap） |
| 2 | `migrations/001_multi_tenant.sql` | tenants / profiles / 旧模板表 / RLS / auth 触发器 |
| 3 | `cloud/001_tenants_seed.sql` | 只初始化租户（不导入旧模板 seed） |
| 4 | `migrations/003_post_auth_setup.sql` | 确保 auth.users 触发器存在 |
| 5 | `migrations/010_add_custom_push_name.sql` | documents.custom_push_name |
| 6 | `migrations/012_add_processing_jobs.sql` | processing_jobs / feishu_push_records |
| 7 | `migrations/013_processing_jobs_worker_claim.sql` | worker 领取函数 |
| 8 | `migrations/020_security_rls_hardening.sql` | RLS 加固 |
| 9 | `migrations/021_configurations.sql` | Configuration / Revision |
| 10 | `migrations/022_results_and_job_revision.sql` | Result 存储与 Job Revision |
| 11 | `migrations/023_drop_legacy_business_tables.sql` | 收尾：删除旧模板表（无业务表时会跳过） |

## 不执行的迁移及原因

- `000_init.sql`：自建 bootstrap（角色/`ALTER ROLE`/storage 表），云上由 Supabase 管理
- `002_init_data.sql`：含旧模板/字段/示例 seed，已由 `cloud/001_tenants_seed.sql` 取代
- `003_electrical_connection.sql`、`004_packaging_*`、`005_schema_sync_functions.sql`、
  `006/007/009/011/014/015/016/019`：旧模板/业务链条，最终由 023 删除，云上不建
- `004_seed_users.sql`、`017/018_*`：写入 `auth.users` 的 seed 与兼容修正；
  云上管理员用户请在 Dashboard 注册后用 SQL 设置 profile（见下）
- `013_add_tenant_settings.sql`：paired-batch 遗留，023 会删除该列

## 管理员用户

1. Dashboard → Authentication → Users → Add user（邮箱 + 密码）
2. 设置租户与角色：

```sql
UPDATE profiles
SET tenant_id = 'a0000000-0000-0000-0000-000000000001',
    role = 'super_admin'
WHERE id = '<auth user id>';
```

## 应用侧 `.env`（云项目）

```env
SUPABASE_URL=https://<project-ref>.supabase.co/rest/v1
SUPABASE_ANON_KEY=<legacy anon JWT 或 sb_publishable_...>
SUPABASE_SERVICE_ROLE_KEY=<legacy service_role JWT 或 sb_secret_...>
JWKS_URL=https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json
JWT_SECRET=
```

> 云项目用户 token 使用非对称签名，API 通过 JWKS 验签（见 issue #14），
> 因此 `JWT_SECRET` 留空即可。
