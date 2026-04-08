-- ============================================================
-- 预置用户种子数据
-- ============================================================
-- 功能：导入初始用户到 auth.users，密码为已加密的 bcrypt hash
-- 执行顺序：在 003_post_auth_setup.sql 之后执行
-- ============================================================

INSERT INTO auth.users (
    id,
    email,
    encrypted_password,
    email_confirmed_at,
    role,
    raw_app_meta_data,
    raw_user_meta_data,
    created_at,
    updated_at,
    aud,
    instance_id
) VALUES
    (
        '4377360e-3965-497b-a333-044398d1d0f5',
        '123@gn.com',
        '$2a$10$C7h6gTg/P2nigHemmLEwkOiyWpqLFI4PP5NOXX23bun1ngDIopVzK',
        '2026-03-13 03:23:49.623845+00',
        'authenticated',
        '{"provider": "email", "providers": ["email"]}',
        '{"tenant_id": "a0000000-0000-0000-0000-000000000001", "display_name": "junmo Ma"}',
        NOW(), NOW(), 'authenticated', '00000000-0000-0000-0000-000000000000'
    ),
    (
        'bc350d6f-edfd-488d-a9c5-1e6b1d9e5305',
        'admin123@gongniu.cn',
        '$2a$10$1qpCUvELDFMkdDyp4RCs/uf7SDT0bnUwe7RRjV7.TdSqLJb7/pu8u',
        '2026-04-08 01:43:34.151011+00',
        'authenticated',
        '{"provider": "email", "providers": ["email"]}',
        '{"tenant_id": "a0000000-0000-0000-0000-000000000002", "display_name": "admin123@gongniu.cn"}',
        NOW(), NOW(), 'authenticated', '00000000-0000-0000-0000-000000000000'
    ),
    (
        '5484211a-7bb5-4f5c-bb4f-5fb13b2b83aa',
        '27694@gn.cn',
        '$2a$10$trK9p2vCnk/Ks3f8mMUnCuONXOmjC6T1eb6lgFdY8eRK2xYEtEl2u',
        '2026-03-31 08:54:43.061393+00',
        'authenticated',
        '{"provider": "email", "providers": ["email"]}',
        '{"tenant_id": "a0000000-0000-0000-0000-000000000002", "display_name": "27694@gn.cn"}',
        NOW(), NOW(), 'authenticated', '00000000-0000-0000-0000-000000000000'
    ),
    (
        '68ac78c2-9e7d-4071-bda0-02bda6e0ce32',
        '244233@gongniu.cn',
        '$2a$10$evZFsh.BWxF6e19bOa2lsevQRbyplJ.XI/erj22fz6X.H7r.YYwhq',
        '2026-03-24 06:04:20.556418+00',
        'authenticated',
        '{"provider": "email", "providers": ["email"]}',
        '{"tenant_id": "a0000000-0000-0000-0000-000000000002", "display_name": "244233@gongniu.cn"}',
        NOW(), NOW(), 'authenticated', '00000000-0000-0000-0000-000000000000'
    ),
    (
        'cd56d93b-7d74-4194-b019-059117e68035',
        '276946@gn.cn',
        '$2a$10$qBuUhr93Vv7ONSzDENcnmOsbGXhAAL5veqo5d7UtOrZbkC7OuedYu',
        '2026-03-30 06:23:06.961401+00',
        'authenticated',
        '{"provider": "email", "providers": ["email"]}',
        '{"tenant_id": "a0000000-0000-0000-0000-000000000001", "display_name": "276946@gn.cn"}',
        NOW(), NOW(), 'authenticated', '00000000-0000-0000-0000-000000000000'
    ),
    (
        'd307e0b5-96f2-4045-b567-fcafb94bf13d',
        '929938267@qq.com',
        '$2a$10$ggx7rKIevHuX51b3mozUBeVNTdzSef6sXKYpMGRq0GrHydSbJS8tq',
        '2026-02-04 07:31:47.887741+00',
        'authenticated',
        '{"provider": "email", "providers": ["email"]}',
        '{"tenant_id": "a0000000-0000-0000-0000-000000000002", "display_name": "junmo Ma"}',
        NOW(), NOW(), 'authenticated', '00000000-0000-0000-0000-000000000000'
    ),
    (
        '9a85d26a-12aa-497f-b605-b600318a256f',
        '277046@gongniu.cn',
        '$2a$10$urq2w.MjsTXiH1BK8Mvo9OR5uC8h2vGgO8pQsUtE0HAjKtneGL.eO',
        '2026-03-24 08:41:33.645056+00',
        'authenticated',
        '{"provider": "email", "providers": ["email"]}',
        '{"tenant_id": "a0000000-0000-0000-0000-000000000001", "display_name": "277046@gongniu.cn"}',
        NOW(), NOW(), 'authenticated', '00000000-0000-0000-0000-000000000000'
    ),
    (
        'c6c8cad7-42d0-4b48-9d86-bd40a558b1fb',
        '273794@gongniu.cn',
        '$2a$10$JfTpL7AW6hLFHPkbPe2OQOJaijoFOeqA5jRIHGEyEhml4EhQKbXJW',
        '2026-03-18 08:04:54.976893+00',
        'authenticated',
        '{"provider": "email", "providers": ["email"]}',
        '{"tenant_id": "a0000000-0000-0000-0000-000000000001", "display_name": "杨杭淇"}',
        NOW(), NOW(), 'authenticated', '00000000-0000-0000-0000-000000000000'
    )
ON CONFLICT (id) DO NOTHING;

SELECT '004_seed_users.sql: 预置用户导入完成，共 8 个用户' AS message;
