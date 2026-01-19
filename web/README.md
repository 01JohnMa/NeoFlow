# OCR 文档智能处理系统 - Web 前端

基于 React + Vite + TailwindCSS 的 OCR 文档智能处理系统前端应用。

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

## 功能特性

- 🔐 用户认证（登录/注册）
- 📤 文档上传（拖拽上传 + 移动端相机拍照）
- 📋 文档列表（分页、筛选、状态显示）
- 👁️ OCR 结果展示
- ✏️ 人工审核修改（字段编辑、验证通过/打回）
- 📱 响应式设计（移动端适配）

## 项目结构

```
src/
├── components/
│   ├── ui/           # 基础 UI 组件 (Button, Input, Card, etc.)
│   └── layout/       # 布局组件 (Sidebar, Header, MainLayout)
├── hooks/
│   ├── useAuth.ts    # 认证 Hook
│   ├── useDocuments.ts # 文档操作 Hook
│   └── useCamera.ts  # 相机 Hook
├── pages/
│   ├── Login.tsx     # 登录页
│   ├── Register.tsx  # 注册页
│   ├── Dashboard.tsx # 仪表盘
│   ├── Upload.tsx    # 上传页
│   ├── Documents.tsx # 文档列表
│   └── DocumentDetail.tsx # 文档详情
├── services/
│   ├── api.ts        # Axios 配置
│   ├── auth.ts       # 认证服务
│   └── documents.ts  # 文档服务
├── store/
│   └── useStore.ts   # Zustand 状态管理
├── lib/
│   ├── utils.ts      # 工具函数
│   └── supabase.ts   # Supabase 客户端
├── types/
│   └── index.ts      # TypeScript 类型定义
├── App.tsx           # 主应用
├── main.tsx          # 入口文件
└── index.css         # 全局样式
```

## 快速开始

### 1. 安装依赖

```bash
cd web
npm install
```

### 2. 配置环境变量

复制 `.env.example` 到 `.env` 并配置:

```bash
# API URL (空则使用代理)
VITE_API_URL=

# Supabase 配置
VITE_SUPABASE_URL=http://localhost:8000
VITE_SUPABASE_ANON_KEY=your-anon-key
```

### 3. 启动开发服务器

```bash
npm run dev
```

访问 http://localhost:3000

### 4. 构建生产版本

```bash
npm run build
```

## 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| Web Frontend | 3000 | Vite 开发服务器 |
| FastAPI | 8080 | 后端 API |
| Supabase API | 8000 | Kong 网关 |
| Supabase Studio | 3001 | 数据库管理界面 |

## API 代理

开发模式下，前端通过 Vite 代理转发 `/api` 请求到后端:

```typescript
// vite.config.ts
server: {
  port: 3000,
  proxy: {
    '/api': {
      target: 'http://localhost:8080',
      changeOrigin: true,
    },
  },
}
```

## 页面路由

| 路径 | 页面 | 认证 |
|------|------|------|
| `/login` | 登录 | 否 |
| `/register` | 注册 | 否 |
| `/` | 仪表盘 | 是 |
| `/upload` | 上传文档 | 是 |
| `/documents` | 文档列表 | 是 |
| `/documents/:id` | 文档详情 | 是 |

## 支持的文档类型

- 📄 检验报告（测试单）
- 📦 快递单
- 📝 抽样单

## 文件格式支持

- PDF
- PNG
- JPG/JPEG
- TIFF
- BMP

最大文件大小: 20MB

## 移动端支持

- 响应式布局
- 触摸友好的 UI
- 相机拍照上传
- 底部导航适配

## 开发说明

### 添加新组件

```tsx
// src/components/ui/MyComponent.tsx
import { cn } from '@/lib/utils'

interface MyComponentProps {
  className?: string
}

export function MyComponent({ className }: MyComponentProps) {
  return (
    <div className={cn('base-classes', className)}>
      Content
    </div>
  )
}
```

### 添加新页面

1. 在 `src/pages/` 创建页面组件
2. 在 `src/App.tsx` 添加路由
3. 如需保护路由，使用 `MainLayout` 包裹

### 状态管理

使用 Zustand 管理全局状态:

```tsx
import { useAuthStore } from '@/store/useStore'

function MyComponent() {
  const { user, isLoading } = useAuthStore()
  // ...
}
```

### 数据请求

使用 TanStack Query:

```tsx
import { useDocumentList } from '@/hooks/useDocuments'

function MyComponent() {
  const { data, isLoading, error } = useDocumentList({ page: 1 })
  // ...
}
```
