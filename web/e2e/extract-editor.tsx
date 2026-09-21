// Development-only fixture; not an application route or a production build entry.
import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { FieldsTab } from '../src/pages/AdminFieldsTab'
import type { Configuration } from '../src/types'
import seed from '../../configurations/seeds/prj-basic-info-drug-registration.json'
import '../src/index.css'

const params = new URLSearchParams(location.search)
function Harness() {
  const [configuration, setConfiguration] = useState({
    id: 'editor-fixture', tenant_id: 'fixture-tenant', project_id: 'fixture-project',
    name: seed.name, code: seed.code, description: seed.description, type: 'extract',
    status: params.has('readonly') ? 'archived' : 'draft',
    draft_definition: seed.definition, current_revision_id: null,
    created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
  } as Configuration)
  return <div className="flex h-screen bg-bg-primary text-text-primary">
    <aside className="w-60 shrink-0 border-r border-border-default p-6">NeoFlow · 编辑器交互测试</aside>
    <div className="min-w-0 flex-1"><header className="h-16 border-b border-border-default px-6 py-5">配置管理</header>
      <main id="editor-scroll" className="h-[calc(100vh-4rem)] overflow-auto p-6">
        <h1 className="mb-5 text-lg">{configuration.name}</h1>
        <FieldsTab configuration={configuration} onUpdated={(next) => {
          setConfiguration(next)
          const win = window as unknown as { savedCount?: number }
          win.savedCount = (win.savedCount ?? 0) + 1
        }} />
      </main>
    </div>
  </div>
}
createRoot(document.getElementById('root')!).render(<StrictMode><Harness /></StrictMode>)
