-- ============================================================
-- 多租户初始化数据脚本
-- ============================================================
-- 功能：创建质量运营部和照明事业部的租户及模板配置
-- 执行顺序：在 001_multi_tenant.sql 之后执行
-- ============================================================

-- ############################################################
-- PART 1: 创建租户
-- ############################################################

-- 1.1 质量运营部
INSERT INTO tenants (id, name, code, description, is_active) VALUES
    ('a0000000-0000-0000-0000-000000000001', '质量运营部', 'quality', '负责产品质量检验报告处理', TRUE)
ON CONFLICT (code) DO NOTHING;

-- 1.2 照明事业部
INSERT INTO tenants (id, name, code, description, is_active) VALUES
    ('a0000000-0000-0000-0000-000000000002', '照明事业部', 'lighting', '负责照明产品测试报告处理', TRUE)
ON CONFLICT (code) DO NOTHING;


-- ############################################################
-- PART 2: 质量运营部模板
-- ############################################################

-- 2.1 检测报告模板
INSERT INTO document_templates (id, tenant_id, name, code, description, process_mode, required_doc_count, is_active, sort_order) VALUES
    ('b0000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001', '检测报告', 'inspection_report', '产品质量检测报告', 'single', 1, TRUE, 1)
ON CONFLICT (tenant_id, code) DO NOTHING;

-- 2.2 快递单模板
INSERT INTO document_templates (id, tenant_id, name, code, description, process_mode, required_doc_count, is_active, sort_order) VALUES
    ('b0000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-000000000001', '快递单', 'express', '外部机构寄达文件快递单', 'single', 1, TRUE, 2)
ON CONFLICT (tenant_id, code) DO NOTHING;

-- 2.3 抽样单模板
INSERT INTO document_templates (id, tenant_id, name, code, description, process_mode, required_doc_count, is_active, sort_order) VALUES
    ('b0000000-0000-0000-0000-000000000003', 'a0000000-0000-0000-0000-000000000001', '抽样单', 'sampling', '市场监督抽样单', 'single', 1, TRUE, 3)
ON CONFLICT (tenant_id, code) DO NOTHING;


-- ############################################################
-- PART 3: 质量运营部模板字段
-- ############################################################

-- 3.1 检测报告字段（18个）
INSERT INTO template_fields (template_id, field_key, field_label, feishu_column, field_type, is_required, sort_order) VALUES
    ('b0000000-0000-0000-0000-000000000001', 'sample_name', '样品名称', '样品名称', 'text', TRUE, 1),
    ('b0000000-0000-0000-0000-000000000001', 'specification_model', '规格型号', '规格型号', 'text', FALSE, 2),
    ('b0000000-0000-0000-0000-000000000001', 'production_date_batch', '生产日期/批号', '生产日期/批号', 'text', FALSE, 3),
    ('b0000000-0000-0000-0000-000000000001', 'inspected_unit_name', '受检单位-名称', '受检单位-名称', 'text', FALSE, 4),
    ('b0000000-0000-0000-0000-000000000001', 'inspected_unit_address', '受检单位-地址', '受检单位-地址', 'text', FALSE, 5),
    ('b0000000-0000-0000-0000-000000000001', 'inspected_unit_phone', '受检单位-电话', '受检单位-电话', 'text', FALSE, 6),
    ('b0000000-0000-0000-0000-000000000001', 'manufacturer_name', '生产单位-名称', '生产单位-名称', 'text', FALSE, 7),
    ('b0000000-0000-0000-0000-000000000001', 'manufacturer_address', '生产单位-地址', '生产单位-地址', 'text', FALSE, 8),
    ('b0000000-0000-0000-0000-000000000001', 'manufacturer_phone', '生产单位-电话', '生产单位-电话', 'text', FALSE, 9),
    ('b0000000-0000-0000-0000-000000000001', 'task_source', '任务来源', '任务来源', 'text', FALSE, 10),
    ('b0000000-0000-0000-0000-000000000001', 'sampling_agency', '抽样机构', '抽样机构', 'text', FALSE, 11),
    ('b0000000-0000-0000-0000-000000000001', 'sampling_date', '抽样日期', '抽样日期', 'date', FALSE, 12),
    ('b0000000-0000-0000-0000-000000000001', 'inspection_conclusion', '检验结论', '检验结论', 'text', FALSE, 13),
    ('b0000000-0000-0000-0000-000000000001', 'inspection_category', '检验类别', '检验类别', 'text', FALSE, 14),
    ('b0000000-0000-0000-0000-000000000001', 'notes', '备注', '备注', 'text', FALSE, 15),
    ('b0000000-0000-0000-0000-000000000001', 'inspector', '主检', '主检', 'text', FALSE, 16),
    ('b0000000-0000-0000-0000-000000000001', 'reviewer', '审核', '审核', 'text', FALSE, 17),
    ('b0000000-0000-0000-0000-000000000001', 'approver', '批准', '批准', 'text', FALSE, 18)
ON CONFLICT (template_id, field_key) DO NOTHING;

-- 3.2 快递单字段（6个）
INSERT INTO template_fields (template_id, field_key, field_label, feishu_column, field_type, is_required, sort_order) VALUES
    ('b0000000-0000-0000-0000-000000000002', 'tracking_number', '快递单号', '快递单号', 'text', TRUE, 1),
    ('b0000000-0000-0000-0000-000000000002', 'recipient', '收件人', '收件人', 'text', FALSE, 2),
    ('b0000000-0000-0000-0000-000000000002', 'delivery_address', '收件地址', '收件地址', 'text', FALSE, 3),
    ('b0000000-0000-0000-0000-000000000002', 'sender', '寄件人', '寄件人', 'text', FALSE, 4),
    ('b0000000-0000-0000-0000-000000000002', 'sender_address', '寄件地址', '寄件地址', 'text', FALSE, 5),
    ('b0000000-0000-0000-0000-000000000002', 'notes', '备注', '备注', 'text', FALSE, 6)
ON CONFLICT (template_id, field_key) DO NOTHING;

-- 3.3 抽样单字段（12个）
INSERT INTO template_fields (template_id, field_key, field_label, feishu_column, field_type, is_required, sort_order) VALUES
    ('b0000000-0000-0000-0000-000000000003', 'task_source', '任务来源', '任务来源', 'text', FALSE, 1),
    ('b0000000-0000-0000-0000-000000000003', 'task_category', '任务类别', '任务类别', 'text', FALSE, 2),
    ('b0000000-0000-0000-0000-000000000003', 'manufacturer', '生产企业', '生产企业', 'text', FALSE, 3),
    ('b0000000-0000-0000-0000-000000000003', 'sample_name', '样品名称', '样品名称', 'text', TRUE, 4),
    ('b0000000-0000-0000-0000-000000000003', 'specification_model', '规格型号', '规格型号', 'text', FALSE, 5),
    ('b0000000-0000-0000-0000-000000000003', 'production_date_batch', '生产日期/批号', '生产日期/批号', 'text', FALSE, 6),
    ('b0000000-0000-0000-0000-000000000003', 'sample_storage_location', '备样封存地点', '备样封存地点', 'text', FALSE, 7),
    ('b0000000-0000-0000-0000-000000000003', 'sampling_channel', '抽样渠道', '抽样渠道', 'text', FALSE, 8),
    ('b0000000-0000-0000-0000-000000000003', 'sampling_unit', '抽样单位', '抽样单位', 'text', FALSE, 9),
    ('b0000000-0000-0000-0000-000000000003', 'sampling_date', '抽样日期', '抽样日期', 'date', FALSE, 10),
    ('b0000000-0000-0000-0000-000000000003', 'sampled_province', '被抽检省份', '被抽检省份', 'text', FALSE, 11),
    ('b0000000-0000-0000-0000-000000000003', 'sampled_city', '被抽检市', '被抽检市', 'text', FALSE, 12)
ON CONFLICT (template_id, field_key) DO NOTHING;


-- ############################################################
-- PART 4: 照明事业部模板
-- ############################################################

-- 4.1 积分球测试模板（子模板，不在前端显示）
INSERT INTO document_templates (id, tenant_id, name, code, description, process_mode, required_doc_count, is_active, sort_order) VALUES
    ('b0000000-0000-0000-0000-000000000010', 'a0000000-0000-0000-0000-000000000002', '积分球测试', 'integrating_sphere', '积分球测试PDF', 'single', 1, FALSE, 1)
ON CONFLICT (tenant_id, code) DO NOTHING;

-- 4.2 光分布测试模板（子模板，不在前端显示）
INSERT INTO document_templates (id, tenant_id, name, code, description, process_mode, required_doc_count, is_active, sort_order) VALUES
    ('b0000000-0000-0000-0000-000000000011', 'a0000000-0000-0000-0000-000000000002', '光分布测试', 'light_distribution', '光分布PDF', 'single', 1, FALSE, 2)
ON CONFLICT (tenant_id, code) DO NOTHING;

-- 4.3 照明综合报告模板（合并模板）
INSERT INTO document_templates (id, tenant_id, name, code, description, process_mode, required_doc_count, is_active, sort_order) VALUES
    ('b0000000-0000-0000-0000-000000000012', 'a0000000-0000-0000-0000-000000000002', '照明综合报告', 'lighting_combined', '积分球+光分布合并报告', 'merge', 2, TRUE, 3)
ON CONFLICT (tenant_id, code) DO NOTHING;


-- ############################################################
-- PART 5: 照明事业部模板字段
-- ############################################################

-- 5.1 积分球测试字段（14个）
INSERT INTO template_fields (template_id, field_key, field_label, feishu_column, field_type, is_required, sort_order, source_doc_type) VALUES
    ('b0000000-0000-0000-0000-000000000010', 'sample_model', '样品型号', '样品型号', 'text', FALSE, 1, '积分球'),
    ('b0000000-0000-0000-0000-000000000010', 'chromaticity_x', '色品坐标X', '色品坐标X', 'text', FALSE, 2, '积分球'),
    ('b0000000-0000-0000-0000-000000000010', 'chromaticity_y', '色品坐标Y', '色品坐标Y', 'text', FALSE, 3, '积分球'),
    ('b0000000-0000-0000-0000-000000000010', 'duv', 'duv', 'duv', 'text', FALSE, 4, '积分球'),
    ('b0000000-0000-0000-0000-000000000010', 'cct', '色温(CCT)', '色温', 'text', FALSE, 5, '积分球'),
    ('b0000000-0000-0000-0000-000000000010', 'ra', 'Ra', 'Ra', 'text', FALSE, 6, '积分球'),
    ('b0000000-0000-0000-0000-000000000010', 'r9', 'R9', 'R9', 'text', FALSE, 7, '积分球'),
    ('b0000000-0000-0000-0000-000000000010', 'cqs', 'CQS', 'CQS', 'text', FALSE, 8, '积分球'),
    ('b0000000-0000-0000-0000-000000000010', 'sdcm', '色容差SDCM', '色容差SDCM', 'text', FALSE, 9, '积分球'),
    ('b0000000-0000-0000-0000-000000000010', 'power_sphere', '功率(积分球)', '功率(积分球)', 'text', FALSE, 10, '积分球'),
    ('b0000000-0000-0000-0000-000000000010', 'luminous_flux_sphere', '光通量(积分球)', '光通量(积分球)', 'text', FALSE, 11, '积分球'),
    ('b0000000-0000-0000-0000-000000000010', 'luminous_efficacy_sphere', '光效(积分球)', '光效(积分球)', 'text', FALSE, 12, '积分球'),
    ('b0000000-0000-0000-0000-000000000010', 'rf', 'Rf', 'Rf', 'text', FALSE, 13, '积分球'),
    ('b0000000-0000-0000-0000-000000000010', 'rg', 'Rg', 'Rg', 'text', FALSE, 14, '积分球')
ON CONFLICT (template_id, field_key) DO NOTHING;

-- 5.2 光分布测试字段（6个）
INSERT INTO template_fields (template_id, field_key, field_label, feishu_column, field_type, is_required, sort_order, source_doc_type) VALUES
    ('b0000000-0000-0000-0000-000000000011', 'lamp_specification', '灯具规格', '灯具规格', 'text', FALSE, 1, '光分布'),
    ('b0000000-0000-0000-0000-000000000011', 'power', '功率', '功率', 'text', FALSE, 2, '光分布'),
    ('b0000000-0000-0000-0000-000000000011', 'luminous_flux', '光通量(光分布)', '光通量(光分布)', 'text', FALSE, 3, '光分布'),
    ('b0000000-0000-0000-0000-000000000011', 'luminous_efficacy', '光效(光分布)', '光效(光分布)', 'text', FALSE, 4, '光分布'),
    ('b0000000-0000-0000-0000-000000000011', 'peak_intensity', '峰值光强', '峰值光强', 'text', FALSE, 5, '光分布'),
    ('b0000000-0000-0000-0000-000000000011', 'beam_angle', '光束角', '光束角', 'text', FALSE, 6, '光分布')
ON CONFLICT (template_id, field_key) DO NOTHING;

-- 5.3 照明综合报告字段（合并所有字段，共20个）
INSERT INTO template_fields (template_id, field_key, field_label, feishu_column, field_type, is_required, sort_order, source_doc_type) VALUES
    -- 来自积分球（14个）
    ('b0000000-0000-0000-0000-000000000012', 'sample_model', '样品型号', '样品型号', 'text', FALSE, 1, '积分球'),
    ('b0000000-0000-0000-0000-000000000012', 'chromaticity_x', '色品坐标X', '色品坐标X', 'text', FALSE, 2, '积分球'),
    ('b0000000-0000-0000-0000-000000000012', 'chromaticity_y', '色品坐标Y', '色品坐标Y', 'text', FALSE, 3, '积分球'),
    ('b0000000-0000-0000-0000-000000000012', 'duv', 'duv', 'duv', 'text', FALSE, 4, '积分球'),
    ('b0000000-0000-0000-0000-000000000012', 'cct', '色温(CCT)', '色温', 'text', FALSE, 5, '积分球'),
    ('b0000000-0000-0000-0000-000000000012', 'ra', 'Ra', 'Ra', 'text', FALSE, 6, '积分球'),
    ('b0000000-0000-0000-0000-000000000012', 'r9', 'R9', 'R9', 'text', FALSE, 7, '积分球'),
    ('b0000000-0000-0000-0000-000000000012', 'cqs', 'CQS', 'CQS', 'text', FALSE, 8, '积分球'),
    ('b0000000-0000-0000-0000-000000000012', 'sdcm', '色容差SDCM', '色容差SDCM', 'text', FALSE, 9, '积分球'),
    ('b0000000-0000-0000-0000-000000000012', 'power_sphere', '功率(积分球)', '功率(积分球)', 'text', FALSE, 10, '积分球'),
    ('b0000000-0000-0000-0000-000000000012', 'luminous_flux_sphere', '光通量(积分球)', '光通量(积分球)', 'text', FALSE, 11, '积分球'),
    ('b0000000-0000-0000-0000-000000000012', 'luminous_efficacy_sphere', '光效(积分球)', '光效(积分球)', 'text', FALSE, 12, '积分球'),
    ('b0000000-0000-0000-0000-000000000012', 'rf', 'Rf', 'Rf', 'text', FALSE, 13, '积分球'),
    ('b0000000-0000-0000-0000-000000000012', 'rg', 'Rg', 'Rg', 'text', FALSE, 14, '积分球'),
    -- 来自光分布（6个）
    ('b0000000-0000-0000-0000-000000000012', 'lamp_specification', '灯具规格', '灯具规格', 'text', FALSE, 15, '光分布'),
    ('b0000000-0000-0000-0000-000000000012', 'power', '功率', '功率', 'text', FALSE, 16, '光分布'),
    ('b0000000-0000-0000-0000-000000000012', 'luminous_flux', '光通量(光分布)', '光通量(光分布)', 'text', FALSE, 17, '光分布'),
    ('b0000000-0000-0000-0000-000000000012', 'luminous_efficacy', '光效(光分布)', '光效(光分布)', 'text', FALSE, 18, '光分布'),
    ('b0000000-0000-0000-0000-000000000012', 'peak_intensity', '峰值光强', '峰值光强', 'text', FALSE, 19, '光分布'),
    ('b0000000-0000-0000-0000-000000000012', 'beam_angle', '光束角', '光束角', 'text', FALSE, 20, '光分布')
ON CONFLICT (template_id, field_key) DO NOTHING;


-- ############################################################
-- PART 6: 照明事业部合并规则
-- ############################################################

INSERT INTO template_merge_rules (template_id, doc_type_a, doc_type_b, sub_template_a_id, sub_template_b_id) VALUES
    ('b0000000-0000-0000-0000-000000000012', '积分球', '光分布', 'b0000000-0000-0000-0000-000000000010', 'b0000000-0000-0000-0000-000000000011')
ON CONFLICT (template_id) DO NOTHING;


-- ############################################################
-- PART 7: 质量运营部模板示例（few-shot）
-- ############################################################

-- 7.1 检测报告示例
INSERT INTO template_examples (template_id, example_input, example_output, description, sort_order, is_active) VALUES
    ('b0000000-0000-0000-0000-000000000001', 
     '检测报告...样品名称：小型断路器...规格型号：LB12-63a C16...生产日期：2025-07-03...受检单位：公牛家装官方旗舰店（武汉市美雀商贸有限公司）...地址：湖北省武汉市江汉区常青路49号恒大御园4栋/单元13层6号...电话：18086049695...生产单位：宁波公牛低压电气有限公司...地址：浙江省慈溪市匡堰镇龙舌村...电话：0574-58586185...任务来源：国家市场监督管理总局...抽样机构：大连产品质量检验检测研究院有限公司...抽样日期：2025-08-14...检验结论：该样品所检项目符合标准要求...检验类别：国家监督抽查...备注：样品购买的电子商务平台：拼多多...主检：马永康...审核：林海石...批准：丛林',
     '{"sample_name": "小型断路器", "specification_model": "LB12-63a C16 AC230/400V 1P", "production_date_batch": "2025-07-03", "inspected_unit_name": "公牛家装官方旗舰店（武汉市美雀商贸有限公司）", "inspected_unit_address": "湖北省武汉市江汉区常青路49号恒大御园4栋/单元13层6号", "inspected_unit_phone": "18086049695", "manufacturer_name": "宁波公牛低压电气有限公司", "manufacturer_address": "浙江省慈溪市匡堰镇龙舌村", "manufacturer_phone": "0574-58586185", "task_source": "国家市场监督管理总局", "sampling_agency": "大连产品质量检验检测研究院有限公司", "sampling_date": "2025-08-14", "inspection_conclusion": "合格", "inspection_category": "国家监督抽查", "notes": "样品购买的电子商务平台：拼多多。", "inspector": "马永康", "reviewer": "林海石", "approver": "丛林"}',
     '检测报告标准示例',
     1, TRUE)
ON CONFLICT DO NOTHING;


-- ############################################################
-- PART 8: 照明事业部模板示例（few-shot）
-- ############################################################

-- 8.1 积分球测试示例
INSERT INTO template_examples (template_id, example_input, example_output, description, sort_order, is_active) VALUES
    ('b0000000-0000-0000-0000-000000000010', 
     '积分球光电参数测试报告...型号：LED-T8-1200...色品坐标：x=0.4523 y=0.4089...Duv：0.0012...色温CCT：3000K...Ra：92.3...R9：85.6...CQS：91.2...SDCM：3.2...功率：18.5W...光通量：1850lm...光效：100lm/W...Rf：89.5...Rg：101.2',
     '{"sample_model": "LED-T8-1200", "chromaticity_x": "0.4523", "chromaticity_y": "0.4089", "duv": "0.0012", "cct": "3000K", "ra": "92.3", "r9": "85.6", "cqs": "91.2", "sdcm": "3.2", "power_sphere": "18.5W", "luminous_flux_sphere": "1850lm", "luminous_efficacy_sphere": "100lm/W", "rf": "89.5", "rg": "101.2"}',
     '积分球测试标准示例',
     1, TRUE)
ON CONFLICT DO NOTHING;

-- 8.2 光分布测试示例
INSERT INTO template_examples (template_id, example_input, example_output, description, sort_order, is_active) VALUES
    ('b0000000-0000-0000-0000-000000000011', 
     '分布光度计测试报告...灯具型号：LED筒灯 Model-A100...功率：15W...光通量：1200lm...光效：80lm/W...峰值光强：850cd...光束角：120°',
     '{"lamp_specification": "LED筒灯 Model-A100", "power": "15W", "luminous_flux": "1200lm", "luminous_efficacy": "80lm/W", "peak_intensity": "850cd", "beam_angle": "120°"}',
     '光分布测试标准示例',
     1, TRUE)
ON CONFLICT DO NOTHING;


-- ############################################################
-- 完成
-- ############################################################

SELECT '002_init_data.sql: 租户和模板初始化数据创建完成！' as message;
SELECT '已创建租户: 质量运营部(quality), 照明事业部(lighting)' as tenants;
SELECT '质量运营部模板: 检测报告, 快递单, 抽样单' as quality_templates;
SELECT '照明事业部模板: 积分球测试, 光分布测试, 照明综合报告(合并模式)' as lighting_templates;
