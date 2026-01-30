# 生产部署计划

> 内网部署地址: `10.10.80.37`
> 创建时间: 2026-01-29

---

## 目录

1. [部署架构](#部署架构)
2. [配置文件调整](#配置文件调整)
3. [容器化部署](#容器化部署)
4. [部署步骤](#部署步骤)
5. [部署检查清单](#部署检查清单)

---

## 部署架构

```
┌─────────────────────────────────────────────────────────────┐
│                        10.10.80.37                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐                │
│  │ Frontend │──▶│  Backend │──▶│ Supabase │                │
│  │   :80    │   │  :8080   │   │  :8000   │                │
│  └──────────┘   └──────────┘   └──────────┘                │
│       │              │              │                       │
│       └──────────────┴──────────────┘                       │
│                      Nginx/Proxy                            │
│                  (可选，统一端口)                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 服务端口

| 服务 | 地址 | 用途 |
|------|------|------|
| 前端 | http://10.10.80.37:80 | 用户界面 |
| 后端 API | http://10.10.80.37:8080 | REST API |
| Supabase | http://10.10.80.37:8000 | 数据库 + Auth |
| Studio | http://10.10.80.37:3001 | Supabase 管理 |

---

## 配置文件调整

### 1. 后端 `.env`

```env
# ============================================
# 生产环境配置（内网部署）
# ============================================

# 应用配置
APP_NAME=OCR-Document-Processor
DEBUG=false
HOST=0.0.0.0
PORT=8080

# Supabase 配置
SUPABASE_URL=http://10.10.80.37:8000

# CORS 配置（允许跨域访问）
CORS_ORIGINS=http://10.10.80.37:3000,http://10.10.80.37:3001,http://10.10.80.37:80
ALLOWED_HOSTS=localhost,127.0.0.1,10.10.80.37

# 安全配置（生产环境必须更换）
SECRET_KEY=your-production-secret-key-at-least-32-chars
LLM_API_KEY=your-production-llm-api-key
```

### 2. Supabase `supabase/.env`

```env
# ============================================
# Supabase 生产配置（内网）
# ============================================

# 公开 URL 配置
API_EXTERNAL_URL=http://10.10.80.37:8000
SITE_URL=http://10.10.80.37:3000
SUPABASE_PUBLIC_URL=http://10.10.80.37:8000

# 安全配置（必须更换）
POSTGRES_PASSWORD=your-secure-password-here
JWT_SECRET=your-long-random-jwt-secret-at-least-32-chars
ANON_KEY=your-production-anon-key
SERVICE_ROLE_KEY=your-production-service-role-key

# 其他配置
DISABLE_SIGNUP=false
```

### 3. 前端 `web/.env`

```env
# ============================================
# 前端生产配置（内网）
# ============================================

VITE_API_URL=http://10.10.80.37:8080
VITE_SUPABASE_URL=http://10.10.80.37:8000
```

---

## 容器化部署

### 目录结构

```
E:\zhuomian\GNEO_AI\sj_ocr\ocr_agentic_system\
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── ...
├── web/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   └── ...
├── supabase/
│   ├── docker-compose.yml
│   ├── .env
│   └── ...
├── docker-compose.yml          # 新增：统一编排
└── .env.production             # 新增：生产环境变量
```

### 1. 后端 Dockerfile

```dockerfile
# api/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖（OCR 相关）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建必要目录
RUN mkdir -p /app/uploads /app/logs

# 暴露端口
EXPOSE 8080

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### 2. 前端 Dockerfile

```dockerfile
# web/Dockerfile
FROM node:20-slim AS builder

WORKDIR /app
COPY package*.json ./
RUN npm install

# 复制生产环境变量
ARG VITE_API_URL
ARG VITE_SUPABASE_URL
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL

COPY . .
RUN npm run build

# 生产镜像
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### 3. 前端 Nginx 配置

```nginx
# web/nginx.conf
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # 前端路由
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 代理
    location /api {
        proxy_pass http://backend:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Supabase 代理
    location /supabase {
        proxy_pass http://supabase:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 4. 统一编排 docker-compose.yml

```yaml
# docker-compose.yml
version: '3.8'

services:
  # Supabase 数据库
  supabase:
    image: supabase/postgres:15
    container_name: ocr-supabase
    restart: unless-stopped
    ports:
      - "8000:8000"
      - "54321:54321"
    environment:
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - JWT_SECRET=${JWT_SECRET}
      - ANON_KEY=${ANON_KEY}
      - SERVICE_ROLE_KEY=${SERVICE_ROLE_KEY}
    volumes:
      - supabase_data:/var/lib/postgresql/data
      - supabase_config:/etc/supabase

  # 后端 API
  backend:
    build:
      context: ./api
      dockerfile: Dockerfile
    container_name: ocr-backend
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      - SUPABASE_URL=http://supabase:8000
      - DEBUG=false
      - SECRET_KEY=${SECRET_KEY}
      - LLM_API_KEY=${LLM_API_KEY}
    volumes:
      - ./api:/app
      - api_uploads:/app/uploads
      - api_logs:/app/logs
    depends_on:
      - supabase

  # 前端
  frontend:
    build:
      context: ./web
      dockerfile: Dockerfile
      args:
        - VITE_API_URL=http://10.10.80.37:8080
        - VITE_SUPABASE_URL=http://10.10.80.37:8000
    container_name: ocr-frontend
    restart: unless-stopped
    ports:
      - "80:80"
    depends_on:
      - backend

volumes:
  supabase_data:
  supabase_config:
  api_uploads:
  api_logs:
```

### 5. 生产环境变量文件

```env
# .env.production
# ============================================
# 生产环境变量（必须修改）
# ============================================

# Supabase 安全配置
POSTGRES_PASSWORD=your-secure-password-at-least-32-chars
JWT_SECRET=your-long-random-jwt-secret-at-least-32-chars
ANON_KEY=your-production-anon-key-from-supabase-console
SERVICE_ROLE_KEY=your-production-service-role-key-from-supabase-console

# 后端安全配置
SECRET_KEY=your-production-secret-key-at-least-32-chars
LLM_API_KEY=your-production-llm-api-key

# 飞书配置（可选）
FEISHU_APP_ID=your-feishu-app-id
FEISHU_APP_SECRET=your-feishu-app-secret
```

---

## 部署步骤

### 方式一：容器化部署（推荐）

```bash
# 1. 复制并修改配置
cp .env.production .env
# 编辑 .env，填入所有密钥

# 2. 构建并启动所有服务
docker-compose up -d --build

# 3. 查看服务状态
docker-compose ps

# 4. 查看日志
docker-compose logs -f

# 5. 初始化数据库（如需要）
docker-compose exec supabase supabase db reset
```

### 方式二：直接部署

```bash
# 1. Supabase
cd supabase
docker-compose up -d

# 2. 前端构建
cd ../web
npm install
npm run build

# 3. 部署前端（任选）
# 方式A: Nginx
# 将 dist/ 放到 nginx 目录
# 方式B: Python
cd dist
python -m http.server 80

# 4. 启动后端
cd ../api
uvicorn main:app --host 0.0.0.0 --port 8080
```

### 方式三：混合部署

```bash
# Supabase 用 Docker，前端和后端直接运行
docker-compose up -d supabase

# 后端
cd api
uvicorn main:app --host 0.0.0.0 --port 8080

# 前端构建
cd ../web
npm run build
# 用 nginx 或 python 托管
```

---

## 部署检查清单

### 部署前

- [ ] 所有密钥已更换（.env.production）
- [ ] DEBUG=false
- [ ] CORS_ORIGINS 包含内网 IP
- [ ] Supabase URL 正确
- [ ] 前端已构建（npm run build）

### 部署后

| 检查项 | 命令/方式 | 预期结果 |
|--------|-----------|----------|
| Supabase 启动 | `docker-compose ps` | Status: Up |
| 后端启动 | `curl http://10.10.80.37:8080/health` | `{"status":"ok"}` |
| 前端访问 | 浏览器打开 http://10.10.80.37:80 | 正常显示页面 |
| API 代理 | 前端发起 API 请求 | 正常返回数据 |
| 数据库连接 | 后端日志无数据库连接错误 | 正常 |

### 常用命令

```bash
# 重启服务
docker-compose restart

# 更新代码后重新部署
docker-compose up -d --build

# 查看实时日志
docker-compose logs -f

# 停止所有服务
docker-compose down

# 停止并删除数据卷（慎用！）
docker-compose down -v
```

---

## FAQ

### Q: 密钥为什么要更换？

| 密钥类型 | 风险 | 后果 |
|----------|------|------|
| 数据库密码 | 当前可能是默认密码 | 任何人可访问数据库 |
| JWT_SECRET | 固定值可被利用 | 可伪造用户登录 |
| LLM_API_KEY | 泄露会产生费用 | 账单增加 |

### Q: 为什么需要 Nginx？

1. **HTTPS** - 浏览器要求 HTTPS 才能使用摄像头等 API
2. **端口统一** - 用户只需访问 80 端口
3. **性能优化** - 静态文件缓存、Gzip 压缩

### Q: 内网可以用 HTTPS 吗？

可以，用 Let's Encrypt 免费证书：
```bash
certbot --nginx -d your-domain.com
```
或者直接用 HTTP（内网安全环境）。

---

## 联系与支持

- 项目路径: `E:\zhuomian\GNEO_AI\sj_ocr\ocr_agentic_system`
- 内网地址: `10.10.80.37`
- 端口: 80 (前端), 8080 (后端), 8000 (Supabase)
