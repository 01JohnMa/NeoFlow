# 服务器用最新代码重新部署（删除旧镜像）

因 SVN 已不可用，需要先把**最新代码**弄到服务器，再在服务器上删旧镜像、用新代码重新构建并启动。数据库卷可保留，用户数据不丢。

---

## 一、把最新代码弄到服务器（三选一）

### 方式 A：用 Git（推荐，若服务器能访问 Git）

在**本机**确保代码已提交并推送到远程（GitHub/Gitea 等），然后在**服务器**上：

```bash
# 若已有仓库，直接拉最新
cd /path/to/neoflow
git fetch && git pull

# 若首次在服务器部署，先克隆
git clone <你的仓库地址> neoflow
cd neoflow
```

### 方式 B：本机打包，服务器解压

在**本机**（项目根目录 neoflow 下）：

```bash
# 排除 node_modules、.git、supabase/volumes、__pycache__ 等
tar --exclude=node_modules --exclude=.git --exclude=supabase/volumes --exclude=api/__pycache__ --exclude=web/node_modules -czvf neoflow-src.tar.gz .
# 或用 zip
# 7z a -xr!node_modules -xr!.git -xr!supabase/volumes neoflow-src.zip .
```

把 `neoflow-src.tar.gz` 传到服务器（scp、FTP、U 盘等），在**服务器**上：

```bash
cd /path/to
mkdir -p neoflow-new && cd neoflow-new
tar -xzvf /path/to/neoflow-src.tar.gz
# 若已有 .env，不要覆盖；若没有，从本机拷一份并改好
```

### 方式 C：rsync 从本机同步到服务器

在**本机**执行（把 10.10.80.37 换成实际服务器 IP，neoflow 换成你本机项目路径）：

```bash
rsync -avz --exclude=node_modules --exclude=.git --exclude=supabase/volumes --exclude=api/__pycache__ \
  e:/zhuomian/GNEO_AI/product_project/neoflow/ \
  user@10.10.80.37:/path/to/neoflow/
```

---

## 二、在服务器上：删旧镜像并用新代码部署

以下在**服务器**上、**已放好最新代码的项目根目录**下执行（即包含 `docker-compose.prod.yml`、`supabase/docker-compose.yml` 的目录）。

### 1. 进入项目目录

```bash
cd /path/to/neoflow
```

### 2. 停掉所有相关容器

```bash
docker compose -f supabase/docker-compose.yml -f docker-compose.prod.yml down
```

### 3. 删除本项目的旧镜像（可选但推荐，避免用错版本）

```bash
# 查看当前 neoflow 相关镜像
docker images | grep -E "neoflow|supabase"

# 删除 neoflow 自己构建的镜像（名字以 neoflow 开头或包含 neoflow 的）
docker rmi neoflow-api neoflow-web 2>/dev/null || true

# 若上面没有删掉，用 IMAGE ID 删（先 docker images 看 ID）
# docker rmi <api镜像ID> <web镜像ID>
```

**注意**：不要删 `supabase/*` 的官方镜像（如 supabase/postgres、kong 等），只删你项目 build 出来的 `neoflow-api`、`neoflow-web`。

### 4. 用最新代码重新构建并启动

```bash
# 使用与 .env 同目录的 .env（若 .env 在项目根）
docker compose -f supabase/docker-compose.yml -f docker-compose.prod.yml build --no-cache
docker compose -f supabase/docker-compose.yml -f docker-compose.prod.yml up -d
```

若希望构建时拉取最新基础镜像，可加 `--pull`：

```bash
docker compose -f supabase/docker-compose.yml -f docker-compose.prod.yml build --no-cache --pull
docker compose -f supabase/docker-compose.yml -f docker-compose.prod.yml up -d
```

### 5. 确认运行正常

```bash
docker compose -f supabase/docker-compose.yml -f docker-compose.prod.yml ps
docker logs neoflow-api --tail 50
docker logs neoflow-ingress --tail 20
```

访问 `http://服务器IP:8080` 验证。

---

## 三、重要：保留数据和配置

- **不要删** `supabase/volumes/db/data`：数据库和用户/Profile 都在这里，删了会丢数据。
- **不要删** `.env`：生产环境变量（Supabase URL、密钥等）在这里；若用方式 B 覆盖了，记得从备份或本机重新拷一份并改好。
- 若服务器上已有 `uploads`、`logs`、`model` 等目录，`docker-compose.prod.yml` 已挂载到 api 容器，无需删除，会继续使用。

---

## 四、一键脚本示例（服务器端）

在服务器项目根目录创建 `redeploy.sh`，内容可为：

```bash
#!/bin/bash
set -e
cd "$(dirname "$0")"
echo "停止容器..."
docker compose -f supabase/docker-compose.yml -f docker-compose.prod.yml down
echo "删除旧镜像..."
docker rmi neoflow-api neoflow-web 2>/dev/null || true
echo "重新构建并启动..."
docker compose -f supabase/docker-compose.yml -f docker-compose.prod.yml build --no-cache
docker compose -f supabase/docker-compose.yml -f docker-compose.prod.yml up -d
echo "完成。检查: docker compose -f supabase/docker-compose.yml -f docker-compose.prod.yml ps"
```

使用前确保**最新代码已在当前目录**，然后执行：`chmod +x redeploy.sh && ./redeploy.sh`。

---

## 五、小结

| 步骤 | 说明 |
|------|------|
| 传代码 | 用 Git pull、打包上传或 rsync，替代已失效的 SVN update |
| 停容器 | `docker compose ... down` |
| 删镜像 | 只删 `neoflow-api`、`neoflow-web`，不删 supabase 官方镜像 |
| 重构建 | `build --no-cache` 确保用当前目录最新代码 |
| 启动 | `up -d` |
| 保留 | 不删 `supabase/volumes/db/data` 和 `.env` |

这样即可在无法使用 SVN 的情况下，用当前最新代码在服务器上重新部署并保留用户数据。
