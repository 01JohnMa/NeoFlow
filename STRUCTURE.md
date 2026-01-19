# 项目结构说明

## 目录树

```
ocr_agentic_system/
│
├── api/                        # FastAPI 应用层
│   ├── __init__.py
│   ├── main.py                # FastAPI 主应用入口
│   └── routes/
│       ├── __init__.py
│       ├── documents.py       # 文档处理路由 (含审核API)
│       └── health.py          # 健康检查路由
│
├── web/                        # React 前端应用 [NEW]
│   ├── src/
│   │   ├── components/        # 组件
│   │   │   ├── ui/           # 基础UI组件
│   │   │   └── layout/       # 布局组件
│   │   ├── pages/            # 页面组件
│   │   │   ├── Login.tsx     # 登录页
│   │   │   ├── Register.tsx  # 注册页
│   │   │   ├── Dashboard.tsx # 仪表盘
│   │   │   ├── Upload.tsx    # 上传页
│   │   │   ├── Documents.tsx # 文档列表
│   │   │   └── DocumentDetail.tsx # 文档详情
│   │   ├── hooks/            # 自定义Hooks
│   │   ├── services/         # API服务
│   │   ├── store/            # 状态管理
│   │   ├── lib/              # 工具库
│   │   └── types/            # TypeScript类型
│   ├── package.json
│   └── vite.config.ts
│
├── agents/                     # LangGraph 智能体
│   ├── __init__.py
│   └── workflow.py            # OCR处理工作流
│
├── config/                     # 配置文件
│   ├── __init__.py
│   ├── settings.py            # 应用配置
│   └── prompts.py             # Prompt配置
│
├── services/                   # 业务服务层
│   ├── __init__.py
│   ├── ocr_service.py         # OCR服务
│   └── supabase_service.py    # Supabase服务
│
├── model/                      # OCR模型 [已下载]
│   ├── PP-OCRv5_server_det_infer/     # 文本检测模型
│   ├── PP-OCRv5_server_rec_infer/     # 文本识别模型
│   ├── PP-LCNet_x1_0_textline_ori_infer/  # 文本行方向模型
│   └── PP-LCNet_x1_0_doc_ori_infer/   # 文档方向模型
│
├── supabase/                   # Supabase本地部署
│   ├── docker-compose.yml     # Docker编排配置
│   ├── kong.yml               # Kong网关配置
│   ├── .env                   # Supabase环境变量
│   ├── migrations/            # 数据库迁移脚本
│   │   └── 000_init_roles.sql
│   └── volumes/               # 数据卷 (gitignore)
│       ├── db/
│       └── storage/
│
├── uploads/                    # 文件上传目录
├── logs/                       # 日志目录
│
├── .env                        # 应用环境变量 (需创建)
├── env.example.txt            # 环境变量模板
├── .gitignore                 # Git忽略配置
├── requirements.txt           # Python依赖
│
├── text_pipline_ocr.py        # [MVP代码] OCR处理
├── supervise_agentic.py       # [MVP代码] LangGraph工作流
├── prompt_config.py           # [MVP代码] Prompt配置
│
├── 实施方案_V2.md              # 调整后的实施方案
├── 实施方案.md                 # 原始实施方案
└── STRUCTURE.md               # 本文件
```

## 快速启动

### 1. 环境准备
```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境 (Windows)
.\venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量
```bash
# 复制配置模板
copy env.example.txt .env

# 编辑 .env 填入 LLM_API_KEY 等配置
```

### 3. 启动Supabase本地服务
```bash
cd supabase
docker-compose up -d
cd ..

# 访问 Supabase Studio: http://localhost:3001
# 执行 migrations/001_init.sql 初始化数据库
```

### 4. 启动API服务
```bash
# 开发模式
uvicorn api.main:app --reload --port 8080

# 或
python -m api.main
```

### 5. 启动前端服务
```bash
cd web
npm install
npm run dev
```

### 6. 测试API
```bash
# 健康检查
curl http://localhost:8080/api/health

# API文档
# 打开浏览器访问: http://localhost:8080/docs
```

## 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| Web Frontend | 3000 | Vite开发服务器 |
| FastAPI | 8080 | 主API服务 |
| Supabase API | 8000 | Kong网关 |
| Supabase Studio | 3001 | 管理界面 |
| PostgreSQL | 5432 | 数据库 |

## MVP代码说明

保留的MVP文件可作为参考：
- `text_pipline_ocr.py` - 原始OCR处理逻辑
- `supervise_agentic.py` - 原始LangGraph工作流
- `prompt_config.py` - 原始Prompt配置

这些代码已经整合到标准项目结构中：
- `text_pipline_ocr.py` → `services/ocr_service.py`
- `supervise_agentic.py` → `agents/workflow.py`
- `prompt_config.py` → `config/prompts.py`
