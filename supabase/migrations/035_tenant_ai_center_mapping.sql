-- AI Center 网关租户映射：tenants 增加平台租户标识列。
--
-- x-ai-center-tenant-id 的取值由中台数据模型决定（applications.tenant_id，
-- 本地部署为 'default'），NeoFlow 不预设其格式，也不在代码里特判具体值：
-- 网关租户一律按本列精确匹配解析为本租户 UUID，未命中即拒绝（未映射）。
-- 历史上 canonicalize 代码里的 default->wetrial 别名与 UUID 直通分支由本迁移取代。

ALTER TABLE public.tenants
    ADD COLUMN IF NOT EXISTS ai_center_tenant_id TEXT;

COMMENT ON COLUMN public.tenants.ai_center_tenant_id IS
    'AI Center 网关租户标识（x-ai-center-tenant-id 的原值）；平台调用按此列映射到本租户，NULL 表示未接入平台';

CREATE UNIQUE INDEX IF NOT EXISTS idx_tenants_ai_center_tenant_id
    ON public.tenants(ai_center_tenant_id)
    WHERE ai_center_tenant_id IS NOT NULL;

-- 本地/验证环境：wetrial 租户对接本地中台的 default 租户。
UPDATE public.tenants
SET ai_center_tenant_id = 'default',
    updated_at = NOW()
WHERE code = 'wetrial'
  AND ai_center_tenant_id IS NULL;
