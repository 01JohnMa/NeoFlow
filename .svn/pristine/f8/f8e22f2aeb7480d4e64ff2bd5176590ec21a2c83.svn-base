# NeoFlow - 智能 OCR-LLM 文档平台

基于 PaddleOCR + LangGraph + LLM 的智能文档识别系统，支持测试单、快递单、抽样单等多类型文档的 OCR 识别与结构化提取。

## 技术栈

| 层级 | 技术选型 |
|------|----------|
| **后端** | FastAPI + LangGraph + PaddleOCR + LLM (GPT-4o/Claude) |
| **前端** | React + TypeScript + Tailwind CSS + shadcn/ui |
| **数据库** | Supabase (PostgreSQL + Auth + Storage) |
| **OCR模型** | PP-OCRv5 (PaddlePaddle) |
| **AI Agent** | LangGraph 工作流编排 |

## 核心功能

- **文档上传** - 支持 PDF、图片批量上传
- **OCR 识别** - PP-OCRv5 高精度文字识别
- **智能提取** - LLM 结构化字段提取（测试单、快递单、抽样单）
- **人工审核** - 识别结果校验与修正
- **数据存储** - Supabase 持久化存储
- **飞书同步** - 审核后自动推送到飞书多维表格
- **多租户** - 基于 Supabase RLS 的用户权限隔离

## 快速启动

### 1. 启动数据库 (Supabase)

```bash
cd supabase
docker-compose up -d

# 首次部署初始化 storage
docker cp storage_base_tables.sql supabase-db:/tmp/
docker exec supabase-db psql -U postgres -d postgres -f /tmp/storage_base_tables.sql
docker restart supabase-storage
```

### 生产部署（单机一体化）

> 说明：以下方式把 web + 后端 + 统一入口（Nginx）与 Supabase 组合部署，外部只暴露 80 端口。

**环境变量**：在仓库根目录放 `.env`，变量名与 `supabase/.env` 一致（如 `ANON_KEY`、`SERVICE_ROLE_KEY`、`POSTGRES_PASSWORD`、`JWT_SECRET`）。可复制 `env.example.txt` 为 `.env` 后按需修改。

```bash
# 在仓库根目录执行
copy env.example.txt .env
# 编辑 .env 后启动
docker compose -f supabase/docker-compose.yml -f docker-compose.prod.yml up -d
```

默认路由：
- `/` → 前端页面
- `/api` → 后端 API
- `/supabase` → Supabase Kong 网关

### 2. 启动后端

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
copy env.example.txt .env
# 编辑 .env 填入 LLM_API_KEY、SUPABASE_*

# 启动服务
uvicorn api.main:app --reload --port 8080
```

### 3. 启动前端

```bash
cd web
npm install
npm run dev
```

## 服务地址

| 服务 | 地址 | 说明 |
|------|------|------|
| 统一入口 | http://localhost | Nginx 入口 |
| API | http://localhost/api | FastAPI 接口 |
| API 文档 | http://localhost/docs | Swagger UI |
| Supabase | http://localhost/supabase | Kong 网关 |
| Studio | http://localhost:3001 | 数据库管理 |

## 项目结构

```
ocr_agentic_system/
├── api/                        # FastAPI 应用层
│   ├── main.py                # 应用入口
│   └── routes/
│       ├── documents.py       # 文档处理路由 (upload/process/query/review)
│       └── health.py          # 健康检查
│
├── web/                        # React 前端
│   ├── src/
│   │   ├── components/        # 组件
│   │   │   ├── ui/           # 基础UI (shadcn/ui)
│   │   │   └── layout/       # 布局组件
│   │   ├── pages/            # 页面
│   │   │   ├── Login.tsx     # 登录
│   │   │   ├── Register.tsx  # 注册
│   │   │   ├── Dashboard.tsx # 仪表盘
│   │   │   ├── Upload.tsx    # 上传
│   │   │   ├── Documents.tsx # 文档列表
│   │   │   └── DocumentDetail.tsx # 文档详情/审核
│   │   ├── hooks/            # 自定义 Hooks
│   │   ├── services/         # API 服务
│   │   ├── store/            # 状态管理
│   │   └── lib/              # 工具库
│   └── vite.config.ts
│
├── agents/                     # LangGraph 智能体
│   └── workflow.py            # OCR 处理工作流
│
├── config/                     # 配置
│   ├── settings.py            # 应用配置
│   └── prompts.py             # LLM Prompt 配置
│
├── services/                   # 业务服务
│   ├── ocr_service.py         # OCR 服务
│   ├── supabase_service.py    # 数据库服务
│   └── feishu_service.py      # 飞书推送服务
│
├── model/                      # PaddleOCR 模型
│   ├── PP-OCRv5_server_det_infer/   # 文本检测
│   ├── PP-OCRv5_server_rec_infer/   # 文本识别
│   ├── PP-LCNet_x1_0_textline_ori_infer/  # 文本行方向
│   └── PP-LCNet_x1_0_doc_ori_infer/ # 文档方向
│
├── supabase/                   # Supabase 本地部署
│   ├── docker-compose.yml     # Docker 编排
│   ├── kong.yml               # Kong 网关
│   ├── migrations/            # 数据库迁移
│   └── .env                   # 环境变量
│
├── .cursor/                    # Cursor IDE 配置
│   └── commands/              # 自定义命令 (UI/UX Pro Max)
│
├── .shared/                    # 共享资源
│   └── ui-ux-pro-max/         # UI/UX 设计系统
│
├── uploads/                    # 上传文件目录
├── logs/                       # 日志目录
├── requirements.txt            # Python 依赖
└── package.json               # 前端依赖
```

## API 接口

### 文档管理

```bash
# 上传文档
POST /api/documents/upload

# 处理文档 (OCR + LLM 提取)
POST /api/documents/{id}/process

# 获取结果
GET /api/documents/{id}/result

# 获取文档列表
GET /api/documents

# 审核通过
PUT /api/documents/{id}/validate

# 打回重做
PUT /api/documents/{id}/reject

# 删除文档
DELETE /api/documents/{id}
```

### 认证

```bash
# 用户注册
POST /api/auth/register

# 用户登录
POST /api/auth/login
```

## 环境变量

```env
# .env 文件

# LLM 配置
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://api.openai.com/v1  # 或其他 LLM API
LLM_MODEL=gpt-4o

# Supabase 配置
SUPABASE_URL=http://localhost:8000
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key

# 飞书配置 (可选)
FEISHU_APP_ID=your-app-id
FEISHU_APP_SECRET=your-app-secret
FEISHU_TABLE_ID=your-table-id
```

## UI/UX Pro Max

本项目使用 UI/UX Pro Max 设计系统进行前端开发，确保专业级的 UI/UX 质量。

### 使用方法

在 Cursor 中使用 `/ui-ux-pro-max` 命令：

```bash
# 生成设计系统
python3 .shared/ui-ux-pro-max/scripts/search.py "ocr llm document platform" --design-system -p "NeoFlow"

# 搜索配色方案 (磨砂玻璃风格)
python3 .shared/ui-ux-pro-max/scripts/search.py "glassmorphism" --domain style

# 搜索组件布局
python3 .shared/ui-ux-pro-max/scripts/search.py "dashboard layout" --stack html-tailwind
```

### 设计规范

- **配色**: 翡翠绿 (#018C39) + 紫色 (#8B5CF6) + 磨砂玻璃质感
- **风格**: 科技简约、暗色主题、毛玻璃卡片
- **图标**: Heroicons SVG 图标
- **字体**: Inter / 中文思源黑体

## 文档类型

| 类型 | display_name 规则 | 说明 |
|------|-------------------|------|
| 测试单 | `报告_{样品名称}_{规格型号}_{抽样日期}` | 检测报告 |
| 快递单 | 自动识别 | 物流单据 |
| 抽样单 | 自动识别 | 抽样记录 |

## 开发日志

| 日期 | 类型 | 内容 |
|------|------|------|
| 2026-01-04 | feat | 添加 React 前端业务页面 |
| 2026-01-06 | feat | 用户权限隔离 (RLS) |
| 2026-01-08 | feat | 飞书多维表格推送服务 |
| 2026-01-13 | refactor | 路由拆分、异常体系重构 |
| 2026-01-13 | feat | pending_review 强制审核流程 |

## 相关文档

- [项目结构详解](./STRUCTURE.md)
- [项目构建经验总结](./项目构建经验总结.md)
- [实施方案](./实施方案_V2.md)
- [Supabase 部署指南](./supabase/README.md)

## License

MIT
