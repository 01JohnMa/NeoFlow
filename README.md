# OCR Agentic System

基于 PaddleOCR + LangGraph 的智能文档识别系统，支持测试单、快递单、抽样单等多类型文档的 OCR 识别与结构化提取。

## 技术栈

- **后端**: FastAPI + LangGraph + PaddleOCR
- **前端**: React + TypeScript + Tailwind CSS
- **数据库**: Supabase (PostgreSQL)
- **模型**: PP-OCRv5

## 快速启动

### 1. 启动数据库

```bash
cd supabase
docker-compose up -d

# 首次部署需初始化 storage（详见 supabase/README.md）
docker cp storage_base_tables.sql supabase-db:/tmp/
docker exec supabase-db psql -U postgres -d postgres -f /tmp/storage_base_tables.sql
docker restart supabase-storage
```

### 2. 启动后端

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
copy env.example.txt .env  # 编辑填入 LLM_API_KEY

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
| 前端 | http://localhost:5173 | Web 界面 |
| API | http://localhost:8080 | 后端接口 |
| API 文档 | http://localhost:8080/docs | Swagger UI |
| Supabase | http://localhost:8000 | 数据库 API |
| Studio | http://localhost:3001 | 数据库管理 |

## 项目结构

```
ocr_agentic_system/
├── api/                 # FastAPI 后端
│   ├── main.py         # 应用入口
│   └── routes/         # 路由（documents, health）
├── web/                 # React 前端
│   └── src/
│       ├── pages/      # 页面（Login, Upload, Documents...）
│       ├── components/ # 组件
│       └── services/   # API 服务
├── agents/              # LangGraph 工作流
├── services/            # 业务服务（OCR, Supabase）
├── config/              # 配置（settings, prompts）
├── model/               # PaddleOCR 模型
├── supabase/            # 数据库部署配置
└── uploads/             # 文件上传目录
```

## 核心功能

1. **文档上传** - 支持 PDF、图片上传
2. **OCR 识别** - PP-OCRv5 高精度文字识别
3. **智能提取** - LLM 结构化字段提取
4. **人工审核** - 识别结果校验与修正
5. **数据存储** - Supabase 持久化存储

## API 接口

```bash
# 上传文档
POST /api/documents/upload

# 处理文档
POST /api/documents/{id}/process

# 获取结果
GET /api/documents/{id}/result

# 审核通过
PUT /api/documents/{id}/validate

# 打回重做
PUT /api/documents/{id}/reject
```

## 环境变量

```env
# .env 文件
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o

SUPABASE_URL=http://localhost:8000
SUPABASE_ANON_KEY=your-anon-key
```

## 相关文档

- [Supabase 部署指南](./supabase/README.md)
- [项目结构详解](./STRUCTURE.md)

