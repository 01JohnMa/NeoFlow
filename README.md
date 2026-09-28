# NeoFlow - 企业文档能力平台

基于 MinerU 版面感知解析 + LLM 的文档处理平台：文档解析为结构化 `ParseResult`（文档 → 页 → 块），各类能力（Parse / Extract / Classify / Split）在统一的 Job / Result 契约上执行，结果以 JSON 形态持久化在 `results` 表。

## 技术栈

| 层级 | 技术选型 |
|------|----------|
| **后端** | FastAPI + LangChain 1.x（OpenAI 兼容 LLM） |
| **前端** | React + TypeScript + Vite + TailwindCSS + Zustand |
| **数据库** | Supabase (PostgreSQL + Auth + PostgREST + RLS) |
| **解析引擎** | MinerU 托管 API（pipeline / vlm 两种模式） |
| **执行架构** | API 受理 + 独立 worker 认领执行 + RPC 原子交卷 |

## 核心概念

- **Configuration / Revision** - 能力配置（草稿 → 发布 → 不可变 Revision）；Extract 配置携带 JSON Schema 子集（Draft 2020-12）与 target
- **Processing Job** - 唯一执行单元。已发布配置 pin Revision；草稿运行 / 参数化能力冻结 `execution_spec` 快照到 Job
- **ParseResult** - 解析产物，是 Extract / Classify / Split 的唯一输入，按文档持久化复用
- **Result** - append-only 结果存储，`sample_key` 区分 `parse` / `extract` / `default`，`engine` 记录执行元信息
- **多租户** - 基于 Supabase RLS 的租户/用户权限隔离

## 能力与执行语义

| 能力 | 状态 | 说明 |
|------|------|------|
| Parse | 已交付 | 受理走 `admit_parse_request`（幂等键 + 活动冲突检测），MinerU 解析，`commit_parse_job` 原子交卷 |
| Extract | 已交付 | JSON Schema 抽取执行器：绑定 ParseResult → 单元执行 → 严格校验 + 至多一次修复 → 认领感知原子交卷（迁移 026–028） |
| Classify / Split | 部分交付 | 消费 ParseResult，独立执行入口已通，流水线编排见 issue #17/#19 |

通用护栏：心跳续租、认领失效即停手、交卷响应丢失回读确认、绝不伪造成功、整单成功/失败无 partial、单元/Job 两级请求预算与 deadline。

## 快速启动

### 1. 启动数据库 (Supabase)

```bash
cd supabase
docker-compose up -d
```

### 生产部署（单机一体化）

> web + 后端 + 统一入口（Nginx ingress 直连 auth/rest）与 Supabase 组合部署，外部只暴露一个端口。

```bash
# 在仓库根目录
cp env.example.txt .env   # 按需修改
docker compose -f supabase/docker-compose.yml -f docker-compose.prod.yml up -d --remove-orphans
```

默认路由：`/` → 前端；`/api` → 后端；`/supabase` → Supabase Auth/REST 直连。

使用外置 PostgreSQL 时，先在目标环境准备数据库，再启动 API/worker：

```bash
docker compose --env-file .env.local \
  -f supabase/docker-compose.external.yml \
  -f docker-compose.prod.yml \
  run --rm --no-deps migrations
```

外置配置不能叠加 `supabase/docker-compose.yml`，否则会引入第二个 `db` 服务和重复端口映射。数据库角色与 Auth 表需预先准备好，Auth 服务启动后再运行迁移。迁移容器只执行 `supabase/migrations` 并记录 `schema_migrations`；它不会把另一套 Supabase 项目中的用户、文档或 Configuration 数据复制过来。LiteLLM 的 URL 和 key 在部署目标环境注入后，再启动 API 与 worker。

全新 PostgreSQL 可以直接使用当前已验证数据库生成的最终基线，跳过历史迁移链：

```bash
docker compose --env-file .env.local \
  -f supabase/docker-compose.external.yml \
  -f docker-compose.prod.yml \
  run --rm --no-deps -e MIGRATION_MODE=baseline -e MIGRATIONS_DIR=/baseline migrations
```

`supabase/baseline` 只包含最终 `public` schema、Auth 兼容函数和 `wetrial` 的药物注册 Configuration；不包含用户、文档、Job、Result 或向量。已有数据库继续使用 `supabase/migrations` 历史链，不能在已有库上运行基线。

### 2. 启动后端 API

```bash
pip install -r requirements.txt
cp env.example.txt .env   # 填入 SUPABASE_*、LLM_API_KEY、MINERU_API_KEY
uvicorn api.main:app --reload --port 8080
```

### 3. 启动文档 worker（独立进程，负责认领并执行 Job）

```bash
python -m workers.document_worker
```

本地测试必须同时保持 API 和 worker 运行。`/api/health` 正常只表示 API 可用；若任务一直是 `queued`、`attempts=0`、`started_at` 为空，应先检查 worker 进程和日志。worker 遇到队列连接的短暂网络错误会等待轮询间隔后重试。

### 4. 启动前端

```bash
cd web
npm install
npm run dev
```

## API 概览

AI Center 调用只允许从私有网络进入；Gateway 校验 Application Key 后转发租户和 capability scope。直接维护或调试时仍可使用 Supabase Auth JWT。管理员接口需租户管理员权限。完整 schema 见 `/docs`（Swagger）。

### 文档

```bash
POST   /api/documents/upload                  # 上传（PDF/图片）
GET    /api/documents                          # 文档列表
GET    /api/documents/{id}/status              # 文档状态
GET    /api/documents/{id}/parse-result        # 文档最新 ParseResult
GET    /api/documents/{id}/download            # 原文件下载
PUT    /api/documents/{id}/rename              # 重命名
DELETE /api/documents/{id}                     # 删除（活动任务占用时 409）
```

### Parse 能力

```bash
POST /api/parse                              # 直接上传文件并异步解析
POST /api/parse/jobs                          # 受理解析（支持 Idempotency-Key 头）
GET  /api/jobs/{job_id}/parse-result          # 指定 Job 的解析结果
```

### Extract 能力

```bash
POST /api/extract                            # 文件 + template_code，直接异步抽取
POST /api/extract/jobs                        # 受理抽取（每文档一个 Job）
GET  /api/documents/{id}/extract-result       # 文档最新正式抽取结果
GET  /api/jobs/{job_id}/extract-result        # 指定 Job 的正式抽取结果
```

直接调用 Extract 时只提交模板编码，不提交 Configuration ID：

```json
{"template_code":"inspection_report"}
```

Parse 不绑定模板。模板编码由 `configurations.code` 提供，服务端按当前租户查找已发布 Extract Configuration，并在 Job 中固定实际 Revision。调用方不提交 `tenant_id`、`department_id`、`configuration_id` 或 `configuration_revision_id`。

### 任务与配置

```bash
GET  /api/jobs                                # 任务列表（按租户/文档/能力过滤）
GET  /api/jobs/{job_id}                       # 任务详情
GET|POST /api/configurations                  # 配置列表/创建
PUT  /api/configurations/{id}                 # 更新草稿
POST /api/configurations/{id}/publish         # 发布为不可变 Revision
POST /api/configurations/{id}/archive         # 归档
GET  /api/configurations/{id}/revisions       # 修订历史
POST /api/sdk/sessions                        # AI 模板向导（草拟抽取配置）
```

租户、配置、SDK 和 Studio 管理接口属于内部管理面，不是 AI Center 对外能力。AI Center 公共合同只导出 Parse、Extract、Job 状态和结果操作；发布预检只执行 `/health`，不会自动创建真实解析或抽取任务。

## 项目结构

```
neoflow/
├── api/
│   ├── main.py                # FastAPI 入口（受理 + 超时恢复后台任务）
│   ├── jobs.py                # Job 读写、认领续租、原子交卷 RPC 封装
│   ├── dependencies/          # 鉴权（JWT/JWKS）
│   └── routes/
│       ├── documents/         # 上传/查询/重命名（子模块）
│       ├── parse.py           # Parse 受理（幂等 + 活动冲突检测）
│       ├── extract.py         # Extract 受理与结果读取
│       ├── configurations.py  # Configuration/Revision 管理
│       ├── jobs.py            # 任务与结果查询
│       ├── sdk.py             # AI 模板向导会话
│       ├── tenants.py         # 租户/用户
│       └── health.py          # 健康检查
├── workers/
│   └── document_worker.py     # 独立 worker：认领 → JobRunner → 原子交卷
├── services/
│   ├── job_runner.py          # 唯一执行 Seam：按能力/配置类型分发 handler
│   ├── parse_service.py       # Parse handler（参数化执行规格）
│   ├── extract_service.py     # Extract handler（绑定/预算/单元/交卷）
│   ├── extract_schema.py      # JSON Schema 子集白名单与取值校验
│   ├── extract_prompt.py      # prompt 构造、严格 JSON 解析、上下文估算
│   ├── llm_invoke.py          # LLM 窄接口（无隐式重试，回传 usage/finish_reason）
│   ├── parse_request_service.py # Parse 受理台账
│   ├── parse_result.py / parser_adapter.py / mineru_adapter.py
│   ├── configuration_service.py # Configuration/Revision 服务
│   ├── result_service.py      # Result 读写（append-only）
│   └── supabase_service.py    # 数据库服务
├── agents/                    # Classify/Split 的 LLM 工作流与结果构建
├── web/                       # React 前端（Parse/Extract Playground、配置管理）
├── supabase/
│   ├── docker-compose.yml     # 本地/生产 Supabase 编排
│   └── migrations/            # 数据库迁移（000–028）
├── tests/                     # pytest（services/routes/workers/db）+ SQL 并发测试
├── docs/
│   ├── adr/                   # 架构决策记录
│   ├── agents/                # 工程协作规范（issue 流程、领域文档）
│   ├── ops/                   # 运维脚本
│   └── archive/               # 已废弃文档归档
├── env.example.txt            # 环境变量示例
└── docker-compose.prod.yml    # 生产部署编排
```

## 环境变量

完整清单见 [env.example.txt](./env.example.txt)，关键项：

```env
# Supabase
SUPABASE_PUBLIC_URL=...
ANON_KEY=...
SERVICE_ROLE_KEY=...
JWT_SECRET=...            # 自建项目用于 API 验签；云项目可改用 JWKS_URL

# LLM（中台部署使用 LiteLLM）
LITELLM_BASE_URL=https://<litellm-gateway>/v1
LITELLM_API_KEY=...       # 由平台部署进程注入，不提交到仓库
LLM_MODEL_ID=deepseek-chat

# 本地直连回退（中台部署不配置）
LLM_API_KEY=...
LLM_BASE_URL=https://api.deepseek.com

# MinerU 解析
MINERU_API_KEY=...
MINERU_BASE_URL=https://mineru.net

# Worker
DOC_WORKER_POLL_INTERVAL_SECONDS=2.0
DOC_WORKER_STALE_LOCK_SECONDS=1800

# Extract 护栏
EXTRACT_MAX_ATTEMPTS=2
EXTRACT_MAX_REQUESTS_PER_JOB=200
EXTRACT_TIMEOUT_SECONDS=900
```

中台应用注册不承载 LiteLLM 凭据。AI Center 部署进程读取平台级 `AINEXUS_RUNTIME_MODEL_GATEWAY_URL` 与 `LITELLM_API_KEY`，创建应用容器时注入为 `LITELLM_BASE_URL` / `LITELLM_API_KEY`。地址在平台部署环境配置一次，key 使用平台的 Runtime Integration virtual key，不是调用 NeoFlow 的 Application API Key。不要把它们加入应用注册表单、Configuration、AI Center manifest 或源码；自托管时才由运维在 `.env` 或部署 Secret 中成对配置。

注册前先准备运行目标可访问的 PostgreSQL、Auth、PostgREST、迁移和已发布模板；`SUPABASE_URL` 指向 PostgREST。发布还需确认中台运行版本支持 `ai-center.yaml` 的独立 worker、API 与 worker 共用持久上传目录，并且两者均收到相同的 LiteLLM/数据库环境变量。平台源码存在 worker 配置不等于运行环境已具备该能力；必须用真实 Job 验证。`/api/health/config` 只显示生效 provider 与 URL，不回显 key，也不能单独证明模型调用成功。

## 测试

```bash
pytest -v                       # 全部
pytest tests/services -v        # 服务层（含 Extract 执行器约 60 个用例）
pytest tests/routes -v          # 路由层
tests/db/run.sh                 # 迁移与 RPC 的 SQL 级并发测试
```

## 相关文档

- [领域术语表](./CONTEXT.md)
- [架构决策记录 (ADR)](./docs/adr/)
- [归档文档索引](./docs/archive/README.md)
- [生产部署说明](./deploy/REDEPLOY_WITH_NEW_CODE.md)

## License

MIT
