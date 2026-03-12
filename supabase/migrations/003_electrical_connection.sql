-- ============================================================
-- 电连接事业部初始化脚本
-- ============================================================
-- 功能：创建电连接事业部的租户、包装模板、packagings结果表及字段配置
-- 执行顺序：在 002_init_data.sql 之后执行
-- ============================================================


-- ############################################################
-- PART 1: 创建 packagings 结果表
-- ############################################################

CREATE TABLE IF NOT EXISTS packagings (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    -- 产品基本信息
    product_name TEXT,
    specification_model TEXT,
    -- USB 规格
    usb_input TEXT,
    usb_single_output TEXT,
    usb_multi_output TEXT,
    -- 产品规格参数
    color TEXT,
    rated_voltage TEXT,
    max_power TEXT,
    max_current TEXT,
    product_length TEXT,
    -- 合规与安全
    execution_standard TEXT,
    precautions JSONB,
    -- 售后与鉴别
    warranty_period TEXT,
    authenticity_method TEXT,
    -- 厂商信息
    address TEXT,
    service_hotline TEXT,
    official_website TEXT,
    recommended_lifespan TEXT,
    -- 标准元数据列
    extraction_confidence FLOAT,
    extraction_version VARCHAR(50) DEFAULT '1.0',
    raw_extraction_data JSONB,
    is_validated BOOLEAN DEFAULT FALSE,
    validated_by UUID,
    validated_at TIMESTAMP WITH TIME ZONE,
    validation_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT packagings_document_unique UNIQUE(document_id)
);

-- 开启 RLS（与其他结果表保持一致）
ALTER TABLE packagings ENABLE ROW LEVEL SECURITY;

-- service_role 可读写所有记录
DROP POLICY IF EXISTS "Service role can manage all packagings" ON packagings;
CREATE POLICY "Service role can manage all packagings" ON packagings
    FOR ALL USING (auth.role() = 'service_role');

-- 用户只能查看自己文档的包装信息
DROP POLICY IF EXISTS "用户可以查看自己文档的包装信息" ON packagings;
CREATE POLICY "用户可以查看自己文档的包装信息" ON packagings
    FOR ALL USING (
        document_id IN (SELECT id FROM documents WHERE user_id = auth.uid())
    );

-- ############################################################
-- PART 2: 创建租户
-- ############################################################

INSERT INTO tenants (id, name, code, description, is_active) VALUES
    ('a0000000-0000-0000-0000-000000000003', '电连接事业部', 'electrical', '负责电连接产品包装信息处理', TRUE)
ON CONFLICT (code) DO NOTHING;


-- ############################################################
-- PART 3: 创建包装模板
-- ############################################################

-- feishu_bitable_token / feishu_table_id 待配置后更新
INSERT INTO document_templates (id, tenant_id, name, code, description, process_mode, required_doc_count, is_active, sort_order) VALUES
    ('b0000000-0000-0000-0000-000000000020', 'a0000000-0000-0000-0000-000000000003', '包装', 'packaging', '包装盒产品信息', 'single', 1, TRUE, 1)
ON CONFLICT (tenant_id, code) DO NOTHING;


-- ############################################################
-- PART 4: 包装模板字段（19个）
-- ############################################################

INSERT INTO template_fields (template_id, field_key, field_label, feishu_column, field_type, is_required, sort_order) VALUES
    ('b0000000-0000-0000-0000-000000000020', 'product_name',         '产品名称',     '产品名称',     'text', FALSE,  1),
    ('b0000000-0000-0000-0000-000000000020', 'specification_model',  '产品型号',     '产品型号',     'text', FALSE,  2),
    ('b0000000-0000-0000-0000-000000000020', 'usb_input',            'USB输入',      'USB输入',      'text', FALSE,  3),
    ('b0000000-0000-0000-0000-000000000020', 'usb_single_output',    'USB单口输出',  'USB单口输出',  'text', FALSE,  4),
    ('b0000000-0000-0000-0000-000000000020', 'usb_multi_output',     'USB多口输出',  'USB多口输出',  'text', FALSE,  5),
    ('b0000000-0000-0000-0000-000000000020', 'color',                '颜色',         '颜色',         'text', FALSE,  6),
    ('b0000000-0000-0000-0000-000000000020', 'rated_voltage',        '额定电压',     '额定电压',     'text', FALSE,  7),
    ('b0000000-0000-0000-0000-000000000020', 'max_power',            '最大功率',     '最大功率',     'text', FALSE,  8),
    ('b0000000-0000-0000-0000-000000000020', 'max_current',          '最大电流',     '最大电流',     'text', FALSE,  9),
    ('b0000000-0000-0000-0000-000000000020', 'product_length',       '产品全长',     '产品全长',     'text', FALSE, 10),
    ('b0000000-0000-0000-0000-000000000020', 'execution_standard',   '执行标准',     '执行标准',     'text', FALSE, 11),
    ('b0000000-0000-0000-0000-000000000020', 'precautions',          '注意事项',     '注意事项',     'text', FALSE, 12),
    ('b0000000-0000-0000-0000-000000000020', 'warranty_period',      '保修时间',     '保修时间',     'text', FALSE, 13),
    ('b0000000-0000-0000-0000-000000000020', 'authenticity_method',  '产品真伪鉴别方法', '产品真伪鉴别方法', 'text', FALSE, 14),
    ('b0000000-0000-0000-0000-000000000020', 'address',              '地址',         '地址',         'text', FALSE, 15),
    ('b0000000-0000-0000-0000-000000000020', 'service_hotline',      '服务热线',     '服务热线',     'text', FALSE, 16),
    ('b0000000-0000-0000-0000-000000000020', 'official_website',     '官网网址',     '官网网址',     'text', FALSE, 17),
    ('b0000000-0000-0000-0000-000000000020', 'recommended_lifespan', '建议使用年限', '建议使用年限', 'text', FALSE, 18)
ON CONFLICT (template_id, field_key) DO NOTHING;

-- ############################################################
-- PART 5: 字段提取提示（extraction_hint）
-- ############################################################

-- product_name：示例中可能为数组，强制要求返回字符串
UPDATE template_fields
SET extraction_hint = '返回单个字符串，不要返回数组'
WHERE template_id = 'b0000000-0000-0000-0000-000000000020'
  AND field_key = 'product_name';

-- specification_model：同上
UPDATE template_fields
SET extraction_hint = '返回单个字符串，不要返回数组'
WHERE template_id = 'b0000000-0000-0000-0000-000000000020'
  AND field_key = 'specification_model';

-- usb_input：以"USB输入:"开头，出现多个取第一个有效值
UPDATE template_fields
SET extraction_hint = '通常以"USB输入:"开头，如出现多个取第一个有效值，返回单个字符串'
WHERE template_id = 'b0000000-0000-0000-0000-000000000020'
  AND field_key = 'usb_input';

-- usb_single_output：将所有口规格按文本顺序合并为一个字符串，用分号分隔
UPDATE template_fields
SET extraction_hint = '将文中所有USB单口的规格合并为一个字符串，按文本出现顺序用分号分隔，例如："USB-C1: 5V==3A/9V=3A/12V=2.5A; USB-A1: 5V-3A/9V=3A/12V=2.5A"，保留原始字符（如"=="或"-"）'
WHERE template_id = 'b0000000-0000-0000-0000-000000000020'
  AND field_key = 'usb_single_output';

-- execution_standard：多个标准号用空格合并
UPDATE template_fields
SET extraction_hint = '如有多个标准号，合并为一个字符串，按原文顺序用空格分隔，如"GB 4943.1-2022 GB 2099.7-2024"'
WHERE template_id = 'b0000000-0000-0000-0000-000000000020'
  AND field_key = 'execution_standard';

-- precautions：返回 JSON 字符串数组，每条注意事项为独立元素
UPDATE template_fields
SET extraction_hint = '以编号列表或段落形式出现，每条注意事项作为独立字符串，返回 JSON 字符串数组格式，如 ["第1条", "第2条"]，保留原文中特殊符号（如⑧）'
WHERE template_id = 'b0000000-0000-0000-0000-000000000020'
  AND field_key = 'precautions';

-- authenticity_method：合并多步骤为一个字符串
UPDATE template_fields
SET extraction_hint = '提取完整鉴别方法，包含扫码、网站、电话等步骤，合并为一个字符串，可用空格连接各步骤，保留原文编号'
WHERE template_id = 'b0000000-0000-0000-0000-000000000020'
  AND field_key = 'authenticity_method';


-- ############################################################
-- PART 6: Few-shot 示例
-- ############################################################

INSERT INTO template_examples (template_id, example_input, example_output, description, sort_order, is_active) VALUES
(
    'b0000000-0000-0000-0000-000000000020',
    '公牛延长线插座(带电源适配器）GNV-MC1303M USB输入:200V-240V~50/60Hz 0.5A USB单口输出 USB-C1: 5V==3A/9V=3A/12V=2.5A USB-C2: 5V==3A/9V=3A/12V=2.5A USB-A1: 5V-3A/9V=3A/12V=2.5A USB-A2: 5V-3A/9V=3A/12V=2.5A USB多口输出:5V=3A 颜色:卵石灰 额定电压:250V~ 最大功率:2500W 最大电流:10A 产品全长:1.5米 执行标准:GB 4943.1-2022 GB 2099.7-2024 注意事项:1.请不要拆卸、改装或短路产品 2.避免强烈摔打 保修时间:1年 地址:浙江省慈溪市观海卫镇工业园东区 服务热线:400-883-2388 官网:www.gonaniu.cr 建议使用年限:5年',
    '{
  "product_name": "公牛延长线插座(带电源适配器）",
  "specification_model": "GNV-MC1303M",
  "usb_input": "200V-240V~50/60Hz 0.5A",
  "usb_single_output": "USB-C1: 5V==3A/9V=3A/12V=2.5A; USB-C2: 5V==3A/9V=3A/12V=2.5A; USB-A1: 5V-3A/9V=3A/12V=2.5A; USB-A2: 5V-3A/9V=3A/12V=2.5A",
  "usb_multi_output": "5V=3A",
  "color": "卵石灰",
  "rated_voltage": "250V~",
  "max_power": "2500W",
  "max_current": "10A",
  "product_length": "1.5米",
  "execution_standard": "GB 4943.1-2022 GB 2099.7-2024",
  "precautions": ["请不要拆卸、改装或短路产品", "避免强烈摔打"],
  "warranty_period": "1年",
  "authenticity_method": "",
  "address": "浙江省慈溪市观海卫镇工业园东区",
  "service_hotline": "400-883-2388",
  "official_website": "www.gonaniu.cr",
  "recommended_lifespan": "5年"
}',
    '包装盒标准示例',
    1,
    TRUE
)
ON CONFLICT DO NOTHING;
