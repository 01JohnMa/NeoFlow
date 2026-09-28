-- ============================================================
-- MIGRATION 032: Rename the default quality tenant for platform registration
-- ============================================================

UPDATE public.tenants
SET name = 'wetrial',
    code = 'wetrial',
    description = 'wetrial 文档处理租户',
    updated_at = NOW()
WHERE id = 'a0000000-0000-0000-0000-000000000001';

INSERT INTO public.tenants (id, name, code, description, is_active)
SELECT
    'a0000000-0000-0000-0000-000000000001',
    'wetrial',
    'wetrial',
    'wetrial 文档处理租户',
    TRUE
WHERE NOT EXISTS (
    SELECT 1 FROM public.tenants
    WHERE id = 'a0000000-0000-0000-0000-000000000001'
);

SELECT pg_notify('pgrst', 'reload schema');
SELECT '032: default tenant renamed to wetrial' AS message;
