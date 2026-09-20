# NeoFlow - Web 前端

基于 React + Vite + TailwindCSS 的 NeoFlow 控制台：文档接入、Parse/Extract 能力运行与验证、配置管理。

## 技术栈

| 层级 | 技术 |
|------|------|
| 框架 | React 19 + Vite 7 |
| 样式 | TailwindCSS 4 |
| 状态管理 | Zustand |
| 路由 | React Router v7 |
| 数据请求 | Axios + TanStack Query |
| 认证 | Supabase Auth |
| 图标 | Lucide React |

## 功能

- 用户认证（登录/注册）
- 文档上传（拖拽 + 移动端相机拍照）与文档列表
- Parse Playground：提交解析、查看页/块结构与 markdown
- Extract Playground：选择配置运行抽取，JSON 树展示结果（复制/下载）
- 配置管理（管理员）：Extract/Classify/Split 配置的草稿编辑、发布、修订历史
- AI 模板向导：从样例文档草拟抽取配置

## 项目结构

```
src/
├── components/
│   ├── ui/                # 基础 UI 组件（Button, Input, Card 等）
│   ├── layout/            # Sidebar / Header / MainLayout
│   ├── admin/             # 配置管理组件
│   ├── parse/             # 解析结果查看组件
│   └── parse-playground/  # Parse Playground
├── pages/
│   ├── Login.tsx / Register.tsx
│   ├── Dashboard.tsx      # 仪表盘
│   ├── Upload.tsx         # 上传
│   ├── Documents.tsx      # 文档列表
│   ├── DocumentDetail.tsx # 文档详情
│   ├── ParseViewer.tsx    # 解析结果查看
│   ├── ParsePlayground.tsx / ExtractPlayground.tsx  # 能力运行与验证
│   ├── AdminConfig.tsx / AdminConfigurationDetail.tsx # 配置管理与修订
│   └── AdminFieldsTab.tsx / AdminRevisionsTab.tsx
├── hooks/                 # useAuth / useDocuments / useJobs / useProfile
├── services/              # API 客户端（auth/documents/parse/extract/configurations/jobs/sdk）
├── store/                 # Zustand 全局状态
└── lib/                   # 工具与纯函数（parseContent/extractSelection/draftingSession 等）
```

## 启动

```bash
npm install
npm run dev       # 开发（Vite dev server）
npm run build     # 生产构建（输出 dist/，供 Docker 部署）
npm run test      # 单元测试（lib 纯函数）
```

环境变量与后端地址配置见仓库根目录 [env.example.txt](../env.example.txt)。
