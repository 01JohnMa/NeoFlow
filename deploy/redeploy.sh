#!/bin/bash
# 在服务器项目根目录执行：删旧镜像、用当前目录最新代码重新构建并启动
# 使用前请先把最新代码放到当前目录（Git pull / 解压包 / rsync）
set -e

COMPOSE_FILES=(-f supabase/docker-compose.yml -f docker-compose.prod.yml)

compose() {
  docker compose "${COMPOSE_FILES[@]}" "$@"
}

cd "$(dirname "$0")/.."
echo "==> 当前目录: $(pwd)"
echo "==> 停止容器..."
compose down
echo "==> 删除旧镜像 (neoflow-api, neoflow-web)..."
docker rmi neoflow-api neoflow-web 2>/dev/null || true
echo "==> 重新构建 (--no-cache)..."
compose build --no-cache
echo "==> 启动..."
compose up -d --remove-orphans
echo "==> 完成。查看状态:"
compose ps
