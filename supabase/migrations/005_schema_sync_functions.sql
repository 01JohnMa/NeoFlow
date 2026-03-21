-- ============================================================
-- 动态模式同步辅助函数（供应用层通过 RPC 调用）
-- 功能：前端在配置页增/改/删模板字段时，后端调用这些函数自动 ALTER TABLE
-- 执行顺序：在 004_packaging_add_product_characteristics.sql 之后
-- ============================================================

-- 结果表白名单（只允许对这些表执行 DDL，防止越权操作）
-- 扩充新表类型时同步在此处追加
-- 系统保留列不允许被 drop/rename

-- ============================================================
-- 函数1：向结果表新增一列（ADD COLUMN）
-- ============================================================
CREATE OR REPLACE FUNCTION add_result_column(
    p_table    TEXT,
    p_column   TEXT,
    p_col_type TEXT DEFAULT 'TEXT'
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_allowed CONSTANT TEXT[] := ARRAY[
        'inspection_reports', 'expresses', 'sampling_forms',
        'lighting_reports', 'packagings',
        'integrating_sphere_reports', 'light_distribution_reports'
    ];
BEGIN
    -- 表名白名单校验
    IF NOT (p_table = ANY(v_allowed)) THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('表 %s 不在允许列表中', p_table)
        );
    END IF;

    -- 列名安全校验（小写字母开头，允许字母/数字/下划线，最长63字符）
    IF p_column !~ '^[a-z][a-z0-9_]{0,62}$' THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format(
                '字段键名 "%s" 不合法（仅允许小写字母、数字、下划线，且须以小写字母开头）',
                p_column
            )
        );
    END IF;

    -- 列已存在则视为成功（幂等）
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = p_table
          AND column_name  = p_column
    ) THEN
        RETURN jsonb_build_object(
            'success', true,
            'message', format('列 %s 已存在于 %s，无需新增', p_column, p_table)
        );
    END IF;

    EXECUTE format('ALTER TABLE %I ADD COLUMN %I TEXT', p_table, p_column);

    -- 通知 PostgREST 刷新 schema 缓存，使新列可被 REST API 立即识别
    PERFORM pg_notify('pgrst', 'reload schema');

    RETURN jsonb_build_object(
        'success', true,
        'message', format('已成功向 %s 新增列 %s', p_table, p_column)
    );
END;
$$;


-- ============================================================
-- 函数2：重命名结果表列（RENAME COLUMN）
-- ============================================================
CREATE OR REPLACE FUNCTION rename_result_column(
    p_table   TEXT,
    p_old_col TEXT,
    p_new_col TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_allowed CONSTANT TEXT[] := ARRAY[
        'inspection_reports', 'expresses', 'sampling_forms',
        'lighting_reports', 'packagings',
        'integrating_sphere_reports', 'light_distribution_reports'
    ];
    v_system_cols CONSTANT TEXT[] := ARRAY[
        'id', 'document_id', 'extraction_confidence', 'extraction_version',
        'raw_extraction_data', 'is_validated', 'validated_by', 'validated_at',
        'validation_notes', 'created_at', 'updated_at'
    ];
BEGIN
    IF NOT (p_table = ANY(v_allowed)) THEN
        RETURN jsonb_build_object('success', false, 'error', format('表 %s 不在允许列表中', p_table));
    END IF;

    IF p_old_col !~ '^[a-z][a-z0-9_]{0,62}$' OR p_new_col !~ '^[a-z][a-z0-9_]{0,62}$' THEN
        RETURN jsonb_build_object('success', false, 'error', '列名不合法（仅允许小写字母、数字、下划线，且须以小写字母开头）');
    END IF;

    -- 禁止改名系统保留列
    IF p_old_col = ANY(v_system_cols) THEN
        RETURN jsonb_build_object('success', false, 'error', format('系统列 %s 不允许重命名', p_old_col));
    END IF;

    -- 新旧相同则跳过（幂等）
    IF p_old_col = p_new_col THEN
        RETURN jsonb_build_object('success', true, 'message', '新旧列名相同，无需操作');
    END IF;

    -- 旧列必须存在
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = p_table AND column_name = p_old_col
    ) THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('列 %s 不存在于表 %s 中', p_old_col, p_table)
        );
    END IF;

    -- 新列名不能已存在（防覆盖）
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = p_table AND column_name = p_new_col
    ) THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('列名 %s 在表 %s 中已存在，请使用其他名称', p_new_col, p_table)
        );
    END IF;

    EXECUTE format('ALTER TABLE %I RENAME COLUMN %I TO %I', p_table, p_old_col, p_new_col);
    PERFORM pg_notify('pgrst', 'reload schema');

    RETURN jsonb_build_object(
        'success', true,
        'message', format('已将 %s 中的列 %s 重命名为 %s', p_table, p_old_col, p_new_col)
    );
END;
$$;


-- ============================================================
-- 函数3：删除结果表列（DROP COLUMN）
-- 默认保护：有历史数据时拒绝，force=true 可强制
-- ============================================================
CREATE OR REPLACE FUNCTION drop_result_column(
    p_table  TEXT,
    p_column TEXT,
    p_force  BOOLEAN DEFAULT FALSE
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_allowed CONSTANT TEXT[] := ARRAY[
        'inspection_reports', 'expresses', 'sampling_forms',
        'lighting_reports', 'packagings',
        'integrating_sphere_reports', 'light_distribution_reports'
    ];
    v_system_cols CONSTANT TEXT[] := ARRAY[
        'id', 'document_id', 'extraction_confidence', 'extraction_version',
        'raw_extraction_data', 'is_validated', 'validated_by', 'validated_at',
        'validation_notes', 'created_at', 'updated_at'
    ];
    v_non_null_count BIGINT;
BEGIN
    IF NOT (p_table = ANY(v_allowed)) THEN
        RETURN jsonb_build_object('success', false, 'error', format('表 %s 不在允许列表中', p_table));
    END IF;

    IF p_column !~ '^[a-z][a-z0-9_]{0,62}$' THEN
        RETURN jsonb_build_object('success', false, 'error', format('列名 %s 不合法', p_column));
    END IF;

    -- 禁止删除系统保留列
    IF p_column = ANY(v_system_cols) THEN
        RETURN jsonb_build_object('success', false, 'error', format('系统列 %s 不允许删除', p_column));
    END IF;

    -- 列不存在时直接视为成功（幂等）
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = p_table AND column_name = p_column
    ) THEN
        RETURN jsonb_build_object('success', true, 'message', format('列 %s 不存在，无需删除', p_column));
    END IF;

    -- 非强制模式下检查是否有历史数据，有则拒绝
    IF NOT p_force THEN
        EXECUTE format('SELECT count(*) FROM %I WHERE %I IS NOT NULL', p_table, p_column)
            INTO v_non_null_count;
        IF v_non_null_count > 0 THEN
            RETURN jsonb_build_object(
                'success', false,
                'error', format(
                    '列 %s 中有 %s 条历史数据，删除将永久丢失。如确认删除，请使用 force=true',
                    p_column, v_non_null_count
                ),
                'non_null_count', v_non_null_count
            );
        END IF;
    END IF;

    EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS %I', p_table, p_column);
    PERFORM pg_notify('pgrst', 'reload schema');

    RETURN jsonb_build_object(
        'success', true,
        'message', format('已从 %s 删除列 %s', p_table, p_column)
    );
END;
$$;


-- ============================================================
-- 函数4：查询结果表的所有列名
-- ============================================================
CREATE OR REPLACE FUNCTION get_result_table_columns(p_table TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_allowed CONSTANT TEXT[] := ARRAY[
        'inspection_reports', 'expresses', 'sampling_forms',
        'lighting_reports', 'packagings',
        'integrating_sphere_reports', 'light_distribution_reports'
    ];
    v_columns TEXT[];
BEGIN
    IF NOT (p_table = ANY(v_allowed)) THEN
        RETURN jsonb_build_object('success', false, 'error', format('表 %s 不在允许列表中', p_table));
    END IF;

    SELECT array_agg(column_name::TEXT ORDER BY ordinal_position)
    INTO v_columns
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name   = p_table;

    RETURN jsonb_build_object(
        'success', true,
        'columns', COALESCE(to_jsonb(v_columns), '[]'::jsonb)
    );
END;
$$;


-- ============================================================
-- 授权 service_role 执行上述函数
-- ============================================================
GRANT EXECUTE ON FUNCTION add_result_column(TEXT, TEXT, TEXT)     TO service_role;
GRANT EXECUTE ON FUNCTION rename_result_column(TEXT, TEXT, TEXT)  TO service_role;
GRANT EXECUTE ON FUNCTION drop_result_column(TEXT, TEXT, BOOLEAN) TO service_role;
GRANT EXECUTE ON FUNCTION get_result_table_columns(TEXT)          TO service_role;
