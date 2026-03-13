# 生产环境保留用户与 Profile 说明

## 1. 数据存在哪里

| 数据 | 位置 | 说明 |
|------|------|------|
| 登录账号 | `auth.users` | Supabase GoTrue，邮箱/密码等 |
| 用户扩展信息 | `public.profiles` | tenant_id、role、display_name |
| 租户 | `public.tenants` | 租户名称、编码等 |

Profile 的 `id` 与 `auth.users.id` 一致，通过触发器在注册时自动创建。

---

## 2. 生产环境“自然保留”（推荐）

只要**不删数据库卷**，用户和 Profile 会一直保留。

- 数据卷：`supabase/volumes/db/data`（见 `docker-compose.yml` 中 db 的 volumes）
- 重启/重新部署容器不会清空数据
- **不要**执行 README 里“重建数据库”那一步（不要 `rm -rf ./volumes/db/data`）

生产环境升级时只用：

```bash
docker compose -f supabase/docker-compose.yml -f docker-compose.prod.yml down
# 不要删 volumes/db/data
docker compose -f supabase/docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## 3. 备份与恢复（防止误删或迁机）

### 备份（在宿主机执行）

```bash
# 备份整个库（含 auth.users + public.profiles + tenants 等）
docker exec supabase-db pg_dump -U postgres -d postgres -Fc -f /tmp/neoflow_backup.dump

# 拷出到宿主机
docker cp supabase-db:/tmp/neoflow_backup.dump ./neoflow_backup_$(date +%Y%m%d).dump
```

### 仅备份用户相关（便于只恢复用户）

```bash
# 仅导出 auth 和 public 下与用户相关的表（自定义格式，可选择性恢复）
docker exec supabase-db pg_dump -U postgres -d postgres \
  -t auth.users -t public.profiles -t public.tenants \
  -Fc -f /tmp/users_profiles.dump
docker cp supabase-db:/tmp/users_profiles.dump ./users_profiles_$(date +%Y%m%d).dump
```

### 恢复

```bash
# 整库恢复（会覆盖当前库，慎用）
docker cp ./neoflow_backup.dump supabase-db:/tmp/
docker exec supabase-db pg_restore -U postgres -d postgres -c --if-exists /tmp/neoflow_backup.dump
```

---

## 4. 从开发环境把用户迁到生产

若在开发库已有一批用户，要迁到生产：

1. **保持 JWT 一致**  
   生产 `.env` 里的 `JWT_SECRET`、`ANON_KEY`、`SERVICE_ROLE_KEY` 若与开发一致，导过去的用户用同一套 token 仍有效；若生产用新 key，用户需要重新登录（密码仍在，只是 token 会变）。

2. **导出开发库用户相关数据**（在开发机执行）  
   ```bash
   docker exec supabase-db pg_dump -U postgres -d postgres \
     -t auth.users -t public.profiles -t public.tenants \
     -Fc -f /tmp/users_profiles.dump
   docker cp supabase-db:/tmp/users_profiles.dump ./users_profiles.dump
   ```

3. **导入到生产**  
   把 `users_profiles.dump` 拷到生产机后：  
   ```bash
   docker cp users_profiles.dump supabase-db:/tmp/
   docker exec supabase-db pg_restore -U postgres -d postgres --data-only --disable-triggers /tmp/users_profiles.dump
   ```  
   若有主键/外键冲突，可先清空生产上 `public.profiles`、`public.tenants` 再导入，或按需写 SQL 做增量同步。

4. **新用户自动有 Profile**  
   生产上已部署 `handle_new_user` 触发器，新注册用户会自动在 `public.profiles` 插入一条记录，无需额外操作。

---

## 5. 小结

| 目标 | 做法 |
|------|------|
| 生产不丢用户/Profile | 不删 `volumes/db/data`，正常 up/down 即可 |
| 防误删/迁机 | 定期用 `pg_dump` 备份，需要时 `pg_restore` |
| 开发用户迁生产 | 导出 auth.users + profiles + tenants，在生产 `pg_restore`，并注意 JWT/Key 是否一致 |
