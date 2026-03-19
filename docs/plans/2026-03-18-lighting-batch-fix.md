# 照明批处理 Single/Merge 问题修复计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 彻底重构照明数据存储——废弃 `lighting_reports` 合并表，改为 `integrating_sphere_reports`（积分球）和 `light_distribution_reports`（光分布）两张独立表，各自只存自己的字段；同时修复 `query.py` 查表逻辑和 `get_extraction_result` 返回 202 的问题。

**Architecture:** 新设计下每个模板对应一张独立业务表，字段完全由模板定义驱动，不再有跨模板的合并存储。`target_table` 字段指向各自的新表。`lighting_reports` 保留但不再写入新数据（兼容历史记录）。

**Tech Stack:** Python, FastAPI, Supabase PostgreSQL, `schema_sync_service`, `supabase_service`

---

## 字段分配

### `integrating_sphere_reports`（积分球，14字段）
| field_key | 说明 |
|---|---|
| sample_model | 样品型号 |
| chromaticity_x | 色品坐标X |
| chromaticity_y | 色品坐标Y |
| duv | duv |
| cct | 色温(CCT) |
| ra | Ra |
| r9 | R9 |
| cqs | CQS |
| sdcm | 色容差SDCM |
| power_sphere | 功率(积分球) |
| luminous_flux_sphere | 光通量(积分球) |
| luminous_efficacy_sphere | 光效(积分球) |
| rf | Rf |
| rg | Rg |

### `light_distribution_reports`（光分布，8字段）
| field_key | 说明 |
|---|---|
| c0_180 | C0/180 |
| c90_270 | C90/270 |
| avg_beam_angle | 平均光束角 |
| lamp_specification | 灯具规格 |
| power | 功率 |
| luminous_flux | 光通量(光分布) |
| luminous_efficacy | 光效(光分布) |
| peak_intensity | 峰值光强 |

---

## Task 1：新建迁移 SQL — 两张独立表

**Files:**
- Create: `supabase/migrations/008_lighting_split_tables.sql`

**Step 1: 创建文件**

```sql
-- ============================================================
-- MIGRATION 008: 拆分 lighting_reports 为两张独立表
-- integrating_sphere_reports：积分球专用（14字段）
-- light_distribution_reports：光分布专用（8字段）
-- lighting_reports 保留，不再写入新数据
-- ============================================================

-- 1. 积分球报告表
CREATE TABLE IF NOT EXISTS integrating_sphere_reports (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,

    -- 积分球字段（14个）
    sample_model              VARCHAR(255),   -- 样品型号
    chromaticity_x            VARCHAR(64),    -- 色品坐标X
    chromaticity_y            VARCHAR(64),    -- 色品坐标Y
    duv                       VARCHAR(64),    -- duv
    cct                       VARCHAR(64),    -- 色温(CCT)
    ra                        VARCHAR(64),    -- Ra
    r9                        VARCHAR(64),    -- R9
    cqs                       VARCHAR(64),    -- CQS
    sdcm                      VARCHAR(64),    -- 色容差SDCM
    power_sphere              VARCHAR(64),    -- 功率(积分球)
    luminous_flux_sphere      VARCHAR(64),    -- 光通量(积分球)
    luminous_efficacy_sphere  VARCHAR(64),    -- 光效(积分球)
    rf                        VARCHAR(64),    -- Rf
    rg                        VARCHAR(64),    -- Rg

    -- 元数据
    extraction_confidence FLOAT,
    extraction_version    VARCHAR(50) DEFAULT '1.0',
    raw_extraction_data   JSONB,
    is_validated          BOOLEAN DEFAULT FALSE,
    validated_by          UUID,
    validated_at          TIMESTAMP WITH TIME ZONE,
    validation_notes      TEXT,
    created_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT integrating_sphere_reports_document_unique UNIQUE(document_id)
);

-- 2. 光分布报告表
CREATE TABLE IF NOT EXISTS light_distribution_reports (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,

    -- 光分布字段（8个）
    c0_180            VARCHAR(64),    -- C0/180
    c90_270           VARCHAR(64),    -- C90/270
    avg_beam_angle    VARCHAR(64),    -- 平均光束角
    lamp_specification VARCHAR(255),  -- 灯具规格
    power             VARCHAR(64),    -- 功率
    luminous_flux     VARCHAR(64),    -- 光通量(光分布)
    luminous_efficacy VARCHAR(64),    -- 光效(光分布)
    peak_intensity    VARCHAR(64),    -- 峰值光强

    -- 元数据
    extraction_confidence FLOAT,
    extraction_version    VARCHAR(50) DEFAULT '1.0',
    raw_extraction_data   JSONB,
    is_validated          BOOLEAN DEFAULT FALSE,
    validated_by          UUID,
    validated_at          TIMESTAMP WITH TIME ZONE,
    validation_notes      TEXT,
    created_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT light_distribution_reports_document_unique UNIQUE(document_id)
);

-- 3. 索引
CREATE INDEX IF NOT EXISTS idx_integrating_sphere_reports_document_id
    ON integrating_sphere_reports(document_id);
CREATE INDEX IF NOT EXISTS idx_integrating_sphere_reports_sample_model
    ON integrating_sphere_reports(sample_model);

CREATE INDEX IF NOT EXISTS idx_light_distribution_reports_document_id
    ON light_distribution_reports(document_id);

-- 4. 更新触发器
CREATE TRIGGER update_integrating_sphere_reports_updated_at
    BEFORE UPDATE ON integrating_sphere_reports
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_light_distribution_reports_updated_at
    BEFORE UPDATE ON light_distribution_reports
    EXECUTE FUNCTION update_updated_at_column();

-- 5. RLS
ALTER TABLE integrating_sphere_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE light_distribution_reports ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role can manage all integrating_sphere_reports"
    ON integrating_sphere_reports FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role can manage all light_distribution_reports"
    ON light_distribution_reports FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "管理员可以查看所有积分球报告" ON integrating_sphere_reports
    FOR ALL USING ((auth.jwt() -> 'app_metadata' ->> 'is_admin')::boolean = true);
CREATE POLICY "管理员可以查看所有光分布报告" ON light_distribution_reports
    FOR ALL USING ((auth.jwt() -> 'app_metadata' ->> 'is_admin')::boolean = true);

-- 6. 更新 target_table 指向新表
UPDATE document_templates
    SET target_table = 'integrating_sphere_reports'
    WHERE code IN ('integrating_sphere', '积分球测试');

UPDATE document_templates
    SET target_table = 'light_distribution_reports'
    WHERE code IN ('light_distribution', '光分布测试');

-- 7. 通知 PostgREST 刷新 schema 缓存
SELECT pg_notify('pgrst', 'reload schema');
```

**Step 2: 在容器内执行**

```bash
docker cp supabase/migrations/008_lighting_split_tables.sql supabase-db:/tmp/
docker exec supabase-db psql -U postgres -d postgres -f /tmp/008_lighting_split_tables.sql
```

预期输出：`CREATE TABLE` × 2，`CREATE INDEX` × 3，`CREATE TRIGGER` × 2，`UPDATE` × 2。

**Step 3: 验证**

```bash
docker exec supabase-db psql -U postgres -d postgres -c \
  "SELECT table_name FROM information_schema.tables WHERE table_name IN ('integrating_sphere_reports','light_distribution_reports');"
```

预期：返回 2 行。

```bash
docker exec supabase-db psql -U postgres -d postgres -c \
  "SELECT code, target_table FROM document_templates WHERE code IN ('integrating_sphere','light_distribution','积分球测试','光分布测试');"
```

预期：`integrating_sphere` → `integrating_sphere_reports`，`light_distribution` → `light_distribution_reports`。

**Step 4: Commit**

```bash
git add supabase/migrations/008_lighting_split_tables.sql
git commit -m "feat: split lighting_reports into integrating_sphere_reports and light_distribution_reports"
```

---

## Task 2：更新 `schema_sync_service` 白名单

**Files:**
- Modify: `supabase/migrations/005_schema_sync_functions.sql`
- Execute: 在容器内重新执行函数定义

**Step 1: 修改白名单**

在 `005_schema_sync_functions.sql` 的 `v_allowed` 数组里加入两张新表：

```sql
-- 修改前
v_allowed CONSTANT TEXT[] := ARRAY[
    'inspection_reports', 'expresses', 'sampling_forms',
    'lighting_reports', 'packagings'
];

-- 修改后
v_allowed CONSTANT TEXT[] := ARRAY[
    'inspection_reports', 'expresses', 'sampling_forms',
    'lighting_reports', 'packagings',
    'integrating_sphere_reports', 'light_distribution_reports'
];
```

此修改需要在 `add_result_column`、`rename_result_column`、`drop_result_column`、`get_result_table_columns` 四个函数里各改一处。

**Step 2: 在容器内重新执行函数定义**

```bash
docker cp supabase/migrations/005_schema_sync_functions.sql supabase-db:/tmp/
docker exec supabase-db psql -U postgres -d postgres -f /tmp/005_schema_sync_functions.sql
```

**Step 3: Commit**

```bash
git add supabase/migrations/005_schema_sync_functions.sql
git commit -m "fix: add new lighting tables to schema_sync whitelist"
```

---

## Task 3：更新 `constants/document_types.py`

**Files:**
- Modify: `constants/document_types.py`

**Step 1: 新增两个枚举值，更新 TABLE_MAP**

```python
class DocumentTypeTable(str, Enum):
    INSPECTION_REPORT = "inspection_reports"
    EXPRESS = "expresses"
    SAMPLING_FORM = "sampling_forms"
    LIGHTING_REPORT = "lighting_reports"          # 保留，兼容历史数据
    INTEGRATING_SPHERE = "integrating_sphere_reports"   # 新增
    LIGHT_DISTRIBUTION = "light_distribution_reports"   # 新增
    PACKAGING = "packagings"

# TABLE_MAP 照明区块改为：
"integrating_sphere":  DocumentTypeTable.INTEGRATING_SPHERE,
"积分球测试":           DocumentTypeTable.INTEGRATING_SPHERE,
"light_distribution":  DocumentTypeTable.LIGHT_DISTRIBUTION,
"光分布测试":           DocumentTypeTable.LIGHT_DISTRIBUTION,
# 旧别名保留兼容
"lighting_combined":   DocumentTypeTable.LIGHTING_REPORT,
"照明综合报告":         DocumentTypeTable.LIGHTING_REPORT,
"照明综合":            DocumentTypeTable.LIGHTING_REPORT,
```

**Step 2: Commit**

```bash
git add constants/document_types.py
git commit -m "feat: add integrating_sphere_reports and light_distribution_reports to TABLE_MAP"
```

---

## Task 4：修复 `query.py` 查表逻辑

**Files:**
- Modify: `api/routes/documents/query.py`:118-122 和 :176-180

**Step 1: 两处 `get_table_name` 改为优先查 `target_table`**

```python
# 第 122 行附近，替换为：
table_name = None
template_id_for_query = document.get("template_id")
if template_id_for_query:
    tpl_row = supabase_service.client.table("document_templates") \
        .select("target_table").eq("id", template_id_for_query).execute()
    table_name = (tpl_row.data[0].get("target_table") or "") if tpl_row.data else ""
if not table_name and document_type:
    table_name = supabase_service.get_table_name(document_type)
```

第 177 行的第二处 `get_table_name` 调用直接删除（复用上面已查到的 `table_name`）。

**Step 2: 验证**

重新触发 single 模式处理光分布文档，查询 `/api/documents/{id}/result`，预期返回 200。

**Step 3: Commit**

```bash
git add api/routes/documents/query.py
git commit -m "fix: use target_table for get_extraction_result table lookup"
```

---

## Task 5：更新 `002_init_data.sql` 中的 `target_table` 初始值

**Files:**
- Modify: `supabase/migrations/002_init_data.sql`

在模板 INSERT 语句里补上 `target_table` 列（供全新部署时直接生效，不依赖 007/008 迁移的 UPDATE）：

```sql
-- 积分球测试模板
INSERT INTO document_templates (id, ..., target_table) VALUES
    ('b0000000-0000-0000-0000-000000000010', ..., 'integrating_sphere_reports')
ON CONFLICT (id) DO UPDATE SET
    target_table = EXCLUDED.target_table, ...;

-- 光分布测试模板
INSERT INTO document_templates (id, ..., target_table) VALUES
    ('b0000000-0000-0000-0000-000000000011', ..., 'light_distribution_reports')
ON CONFLICT (id) DO UPDATE SET
    target_table = EXCLUDED.target_table, ...;
```

**Step 2: Commit**

```bash
git add supabase/migrations/002_init_data.sql
git commit -m "fix: set target_table in init_data for lighting templates"
```

---

## Task 6：重启 API 容器清除列名缓存

`schema_sync_service` 有内存列名缓存，需要重启才能识别新表。

```bash
docker restart neoflow-api
```

验证：
```bash
docker logs neoflow-api --tail 20
```

预期：`Application startup complete.`

---

## 验证清单

完成以上 Task 后，重新触发一次完整批处理：

- [ ] single 光分布：数据写入 `light_distribution_reports`，无 WARNING
- [ ] single 积分球：数据写入 `integrating_sphere_reports`
- [ ] `/result` 接口：返回 200，数据完整
- [ ] merge 模式：文档 A 写 `integrating_sphere_reports`，文档 B 写 `light_distribution_reports`，配对关系正确
- [ ] 双方审核后：合并推送飞书，字段完整
