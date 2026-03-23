# 生产部署与用户数据迁移手册（可复用）

本文档描述：**用新版本代码重建数据库结构**，**仅保留用户登录与 Profile**（`auth.users` + `public.profiles`），**不保留业务数据**（文档、OCR 结果等）时的标准流程。

适用场景：

- 默认租户仅为 `quality` / `lighting`，用户为**邮箱密码**登录；
- `uploads` 等业务文件可按需决定是否保留（本流程默认不依赖迁移 uploads）；
- 容器名以仓库内 `docker-compose` 为准（见下文）。

---

## 一、关键约定（勿改容器名）

| 组件 | 容器名 | 配置文件 |
|------|--------|----------|
| PostgreSQL | `supabase-db` | `supabase/docker-compose.yml` → `db` |
| 迁移执行器 | `supabase-migrations` | 同上 |
| API / Web / 入口 | `neoflow-api` / `neoflow-web` / `neoflow-ingress` | `docker-compose.prod.yml` |

**所有 `docker exec`、`pg_dump` 一律使用容器名 `supabase-db`。**

Compose 启动命令（在项目根目录，与 `docker-compose.prod.yml` 同级）：

```bash
docker compose -f supabase/docker-compose.yml -f docker-compose.prod.yml <子命令>
```

---

## 二、SVN 仓库路径说明（若使用 SVN）

若 `svn ls` 显示目录名为 `neoflow /`（`neoflow` 与 `/` 之间有空格），则远程路径实际为带尾部空格的目录，检出或切换时需使用 URL 编码：

```text
https://<服务器>/svn/<仓库>/neoflow%20
```

错误示例：使用 `.../neoflow` 会报 `Target path '/neoflow' does not exist`。

---

## 三、迁移策略概览

| 目标 | 做法 |
|------|------|
| 数据库结构 | 以新代码为准：清空 `supabase/volumes/db/data` 后重新初始化 |
| 用户账号与资料 | 从旧库导出 `auth.users`、`public.profiles`，导入新库 |
| 业务数据 | 不迁移（新库初始化 + migration 生成模板等） |
| 环境变量 | **必须保留** 生产用项目根 `.env`；若使用 `supabase/.env` 也需一并保留，勿用模板整文件覆盖 |

---

## 四、阶段 A：在旧数据仍可访问时完成备份

> **在删除或替换 `supabase/volumes/db/data` 之前必须完成本节。**

### A.1 仅用「旧项目目录」启动数据库

在**仍挂载旧数据卷**的目录（例如 `neoflow_bak_YYYYMMDD`）下：

```bash
cd /path/to/neoflow_bak_YYYYMMDD
docker compose -f supabase/docker-compose.yml up -d db
```

确认：

```bash
docker ps --filter "name=supabase-db"
docker exec supabase-db pg_isready -U postgres
```

若提示容器名冲突，先停止其他目录已启动的 compose：`docker compose ... down`，或 `docker stop supabase-db`（谨慎，确认无其他服务依赖）。

### A.2 创建备份目录

```bash
mkdir -p /home/caigou/backups
```

（路径可按服务器规范修改，下文以 `/home/caigou/backups` 为例。）

### A.3 全库备份（强烈建议）

```bash
docker exec supabase-db pg_dump -U postgres -d postgres \
  -Fc -f /tmp/neoflow_full.dump

docker cp supabase-db:/tmp/neoflow_full.dump \
  /home/caigou/backups/neoflow_full_$(date +%Y%m%d).dump
```

### A.4 仅导出用户相关表（必做）

```bash
docker exec supabase-db pg_dump -U postgres -d postgres \
  -t auth.users \
  -t public.profiles \
  --data-only \
  --column-inserts \
  -f /tmp/neoflow_users_only.sql

docker cp supabase-db:/tmp/neoflow_users_only.sql \
  /home/caigou/backups/neoflow_users_only_$(date +%Y%m%d).sql
```

### A.5 记录行数（便于后续核对）

```bash
docker exec -i supabase-db psql -U postgres -d postgres -c \
"SELECT 'auth.users' AS t, count(*) FROM auth.users
 UNION ALL SELECT 'public.profiles', count(*) FROM public.profiles;"
```

### A.6 停止旧目录上的数据库

```bash
cd /path/to/neoflow_bak_YYYYMMDD
docker compose -f supabase/docker-compose.yml down
```

---

## 五、阶段 B：部署新代码并保留配置

1. 将新代码放到目标目录（如 `neoflow_new` 或替换后的 `neoflow`）。
2. **从备份拷贝生产环境变量**（示例）：

   ```bash
   cp /path/to/neoflow_bak_YYYYMMDD/.env /path/to/neoflow_new/.env
   # 若存在：
   cp /path/to/neoflow_bak_YYYYMMDD/supabase/.env /path/to/neoflow_new/supabase/.env
   ```

3. **不要用** `env.example.txt` 整文件覆盖生产 `.env`。

---

## 六、阶段 C：清空旧 Postgres 数据卷并启动新栈

> **会删除该目录下所有数据库业务数据**（用户数据靠阶段 A 的 SQL 恢复）。

```bash
cd /path/to/neoflow_new/supabase
sudo mv volumes/db/data "volumes/db/data_backup_$(date +%Y%m%d)"
sudo mkdir -p volumes/db/data
# 属主与权限需与镜像一致，常见为 postgres 用户 uid（如 999），以现场 ls -la 为准
sudo chown -R 999:999 volumes/db/data 2>/dev/null || true
```

在项目根：

```bash
cd /path/to/neoflow_new
docker compose -f supabase/docker-compose.yml -f docker-compose.prod.yml down
docker compose -f supabase/docker-compose.yml -f docker-compose.prod.yml build --no-cache
docker compose -f supabase/docker-compose.yml -f docker-compose.prod.yml up -d
```

确认 `supabase-db` 健康、`supabase-migrations` 日志无致命错误：

```bash
docker compose -f supabase/docker-compose.yml -f docker-compose.prod.yml ps
docker logs supabase-migrations 2>&1 | tail -80
```

---

## 七、阶段 D：导入用户数据

导入前需**暂时关闭** `auth.users` 上的「新用户自动创建 profile」触发器，避免与备份中的 `public.profiles` 冲突。

### D.1 查询触发器名

```bash
docker exec -i supabase-db psql -U postgres -d postgres -c \
"SELECT tgname FROM pg_trigger WHERE NOT tgisinternal AND tgrelid = 'auth.users'::regclass;"
```

一般为 `on_auth_user_created`。

### D.2 禁用触发器

```bash
docker exec -i supabase-db psql -U postgres -d postgres -c \
"ALTER TABLE auth.users DISABLE TRIGGER on_auth_user_created;"
```

### D.3 拷贝 SQL 并执行导入

```bash
docker cp /home/caigou/backups/neoflow_users_only_YYYYMMDD.sql supabase-db:/tmp/neoflow_users_only.sql

docker exec -i supabase-db psql -U postgres -d postgres -v ON_ERROR_STOP=1 -f /tmp/neoflow_users_only.sql
```

将 `YYYYMMDD` 换为实际文件名日期。

### D.4 启用触发器

```bash
docker exec -i supabase-db psql -U postgres -d postgres -c \
"ALTER TABLE auth.users ENABLE TRIGGER on_auth_user_created;"
```

---

## 八、阶段 E：数据库验收

```bash
docker exec -i supabase-db psql -U postgres -d postgres -c \
"SELECT count(*) AS users FROM auth.users; SELECT count(*) AS profiles FROM public.profiles;"

docker exec -i supabase-db psql -U postgres -d postgres -c \
"SELECT u.id, u.email FROM auth.users u
 LEFT JOIN public.profiles p ON p.id = u.id
 WHERE p.id IS NULL LIMIT 10;"

docker exec -i supabase-db psql -U postgres -d postgres -c \
"SELECT p.id, p.tenant_id, t.code FROM public.profiles p
 LEFT JOIN public.tenants t ON t.id = p.tenant_id
 WHERE p.tenant_id IS NOT NULL AND t.id IS NULL;"
```

期望：第二、三段查询**无异常行**（或第二段为空）。

---

## 九、阶段 F：应用验收

- 访问入口（默认经 `neoflow-ingress`，常见为 `http://<服务器IP>:8080`，以 `.env` 中 `INGRESS_HTTP_PORT` 为准）。
- 抽样 2～3 个账号登录，确认租户与权限正常。
- 必要时查看日志：

  ```bash
  docker logs neoflow-api --tail 100
  docker logs neoflow-ingress --tail 50
  ```

---

## 十、常见问题

| 现象 | 处理 |
|------|------|
| `docker cp` 报目录不存在 | 先 `mkdir -p /home/caigou/backups` |
| 导入时主键/唯一约束冲突 | 新库中已有同邮箱或同 id 用户；删除测试数据或调整导出范围后重导 |
| 未禁用触发器即导入 | 可能导致 `profiles` 冲突；应清空相关表后按 D 节重导（需评估影响） |
| `supabase-storage` 短暂 unhealthy | 查看日志若已为 `Server listening`，多为健康检查滞后，可 `curl http://127.0.0.1:5000/status` 验证 |
| Compose 提示 `version` obsolete | 可忽略，不影响运行 |

---

## 十一、复用检查清单

- [ ] 阶段 A 已完成：全库 `.dump` + `neoflow_users_only_*.sql` 已保存到安全路径  
- [ ] 生产 `.env`（及 `supabase/.env`）已恢复，未被模板覆盖  
- [ ] 已按需清空 `supabase/volumes/db/data` 并启动新栈  
- [ ] `supabase-migrations` 已成功执行  
- [ ] 已 **DISABLE TRIGGER → 导入 → ENABLE TRIGGER**  
- [ ] 阶段 E、F 验收通过  

---

## 十二、相关文档

- 仅更新代码、尽量保留原数据库卷：`deploy/REDEPLOY_WITH_NEW_CODE.md`  
- Supabase 本地说明：`supabase/README.md`

---

*文档版本：与仓库 `supabase/docker-compose.yml`、`docker-compose.prod.yml` 中的 `container_name` 保持一致；若本地修改过容器名，请同步替换本文命令。*
