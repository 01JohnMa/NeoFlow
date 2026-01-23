---
name: Fix Web Build Errors
overview: 修复前端 build 阶段的 TypeScript/配置错误，确保 `npm run build` 可通过并可用于 preview 验证手机拍照刷新问题。
todos:
  - id: add-vite-env-types
    content: 新增 vite-env.d.ts 以修复 env/png 类型错误。
    status: completed
  - id: cleanup-unused-imports
    content: 清理 Dashboard/Documents/DocumentDetail 未使用项。
    status: completed
  - id: fix-extraction-casts
    content: 修复 DocumentDetail 的 ExtractionResult 类型断言。
    status: completed
  - id: update-tsconfig-node
    content: 移除 tsconfig.node.json 中不支持的配置。
    status: completed
isProject: false
---

# 计划：修复前端构建错误

## 目标

- 解决 `npm run build` 报错（类型声明、未使用变量、类型断言、TS 配置不兼容）。

## 修改范围

- [`web/src/vite-env.d.ts`](web/src/vite-env.d.ts)：新增 Vite 类型引用与静态资源声明，修复 `import.meta.env` 与 `png` 导入报错。
- [`web/src/components/layout/Sidebar.tsx`](web/src/components/layout/Sidebar.tsx)：确认 `Logo` 导入依赖的类型声明后保持不变。
- [`web/src/services/api.ts`](web/src/services/api.ts)、[`web/src/lib/supabase.ts`](web/src/lib/supabase.ts)：依赖 `vite-env.d.ts` 的 `ImportMetaEnv` 类型。
- [`web/src/pages/Dashboard.tsx`](web/src/pages/Dashboard.tsx)：移除未使用的 `profile`、`tenantCode` 解构项。
- [`web/src/pages/Documents.tsx`](web/src/pages/Documents.tsx)：移除未使用的导入（`CardHeader`、`CardTitle`、`Eye`、`Search`）。
- [`web/src/pages/DocumentDetail.tsx`](web/src/pages/DocumentDetail.tsx)：移除未使用图标 `Clock`，并将 `extraction_data` 的类型断言改为安全的 `unknown` 再转 `Record<string, unknown>`。
- [`web/tsconfig.node.json`](web/tsconfig.node.json)：移除不被当前 TS 版本支持的 `erasableSyntaxOnly` 选项。

## 关键修复点

- 新增 `vite-env.d.ts`（无该文件导致 `import.meta.env` 与 `png` 类型报错）：
```1:6:web/src/vite-env.d.ts
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string
  readonly VITE_SUPABASE_URL?: string
  readonly VITE_SUPABASE_ANON_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare module '*.png' {
  const src: string
  export default src
}
```

- `DocumentDetail` 中三处强制断言改为 `as unknown as Record<string, unknown>`，避免 TS2352。

## 验证步骤

- 运行 `npm run build` 确认无报错。
- 如需验证手机拍照刷新问题，再运行 `npm run preview -- --host`。