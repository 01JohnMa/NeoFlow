-- ============================================================
-- 多租户初始化数据脚本
-- ============================================================
-- 功能：创建质量管理中心和照明事业部的租户及模板配置
-- 执行顺序：在 001_multi_tenant.sql 之后执行
-- ============================================================

-- ############################################################
-- PART 1: 创建租户
-- ############################################################

-- 1.1 质量管理中心
INSERT INTO tenants (id, name, code, description, is_active) VALUES
    ('a0000000-0000-0000-0000-000000000001', '质量管理中心', 'quality', '负责产品质量检验报告处理', TRUE)
ON CONFLICT (code) DO NOTHING;

-- 1.2 照明事业部
INSERT INTO tenants (id, name, code, description, is_active) VALUES
    ('a0000000-0000-0000-0000-000000000002', '照明事业部', 'lighting', '负责照明产品测试报告处理', TRUE)
ON CONFLICT (code) DO NOTHING;


-- ############################################################
-- PART 2: 质量管理中心模板
-- ############################################################

-- 2.1 检测报告模板
INSERT INTO document_templates (id, tenant_id, name, code, description, required_doc_count, push_attachment, is_active, sort_order) VALUES
    ('b0000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001', '检测报告', 'inspection_report', '产品质量检测报告', 1, TRUE, TRUE, 1)
ON CONFLICT (tenant_id, code) DO NOTHING;

-- 2.2 快递单模板
INSERT INTO document_templates (id, tenant_id, name, code, description, required_doc_count, push_attachment, is_active, sort_order) VALUES
    ('b0000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-000000000001', '快递单', 'express', '外部机构寄达文件快递单', 1, FALSE, TRUE, 2)
ON CONFLICT (tenant_id, code) DO NOTHING;

-- 2.3 抽样单模板（extraction_mode=vlm）
INSERT INTO document_templates (id, tenant_id, name, code, description, required_doc_count, push_attachment, extraction_mode, is_active, sort_order) VALUES
    ('b0000000-0000-0000-0000-000000000003', 'a0000000-0000-0000-0000-000000000001', '抽样单', 'sampling', '市场监督抽样单', 1, TRUE, 'vlm', TRUE, 3)
ON CONFLICT (tenant_id, code) DO NOTHING;


-- ############################################################
-- PART 3: 质量管理中心模板字段
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

-- 检测报告：检验结论强制审核（合格/不合格）
UPDATE template_fields
SET review_enforced = TRUE,
    review_allowed_values = '["合格","不合格"]'::jsonb
WHERE template_id = 'b0000000-0000-0000-0000-000000000001'
  AND field_key = 'inspection_conclusion';

-- 检测报告：检验结论提取提示
UPDATE template_fields
SET extraction_hint = '将检测结论表述都转为合格或者不合格，不确定就为无法确定'
WHERE template_id = 'b0000000-0000-0000-0000-000000000001'
  AND field_key = 'inspection_conclusion';

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
-- PART 7: 质量管理中心模板示例（few-shot）
-- ############################################################

-- 7.1 检测报告示例
INSERT INTO template_examples (id, template_id, example_input, example_output, description, sort_order, is_active) VALUES
    ('c0000000-0000-0000-0000-000000000001',
     'b0000000-0000-0000-0000-000000000001', 
     '检测报告...样品名称：小型断路器...规格型号：LB12-63a C16...生产日期：2025-07-03...受检单位：公牛家装官方旗舰店（武汉市美雀商贸有限公司）...地址：湖北省武汉市江汉区常青路49号恒大御园4栋/单元13层6号...电话：18086049695...生产单位：宁波公牛低压电气有限公司...地址：浙江省慈溪市匡堰镇龙舌村...电话：0574-58586185...任务来源：国家市场监督管理总局...抽样机构：大连产品质量检验检测研究院有限公司...抽样日期：2025-08-14...检验结论：该样品所检项目符合标准要求...检验类别：国家监督抽查...备注：样品购买的电子商务平台：拼多多...主检：马永康...审核：林海石...批准：丛林',
     '{"sample_name": "小型断路器", "specification_model": "LB12-63a C16 AC230/400V 1P", "production_date_batch": "2025-07-03", "inspected_unit_name": "公牛家装官方旗舰店（武汉市美雀商贸有限公司）", "inspected_unit_address": "湖北省武汉市江汉区常青路49号恒大御园4栋/单元13层6号", "inspected_unit_phone": "18086049695", "manufacturer_name": "宁波公牛低压电气有限公司", "manufacturer_address": "浙江省慈溪市匡堰镇龙舌村", "manufacturer_phone": "0574-58586185", "task_source": "国家市场监督管理总局", "sampling_agency": "大连产品质量检验检测研究院有限公司", "sampling_date": "2025-08-14", "inspection_conclusion": "合格", "inspection_category": "国家监督抽查", "notes": "样品购买的电子商务平台：拼多多。", "inspector": "马永康", "reviewer": "林海石", "approver": "丛林"}',
     '检测报告标准示例',
     1, TRUE)
ON CONFLICT (id) DO NOTHING;

-- 7.2 快递单示例
INSERT INTO template_examples (id, template_id, example_input, example_output, description, sort_order, is_active) VALUES
    ('c0000000-0000-0000-0000-000000000002',
     'b0000000-0000-0000-0000-000000000002', 
     '顺丰速运...运单号：1391451353025...寄件人：黄海花 020-32293669...寄件地址：广东省广州市黄埔区开泰大道天泰一路3号（威凯检测技术有限公司）...收件人：王伟 0574-58586166...收件地址：浙江省宁波市慈溪市观海卫镇观附公路28号（宁波公牛数码科技有限公司）...内件品名：充电宝（移动电源）-20251120111511309-样品确认通知书+抽样单第三联一生产',
     '{"tracking_number": "1391451353025", "sender": "黄海花020-32293669", "sender_address": "广东省广州市黄埔区开泰大道天泰一路3号（威凯检测技术有限公司）", "recipient": "王伟0574-58586166", "delivery_address": "浙江省宁波市慈溪市观海卫镇观附公路28号（宁波公牛数码科技有限公司）", "notes": "充电宝（移动电源）-20251120111511309-样品确认通知书+抽样单第三联一生产"}',
     '快递单标准示例',
     1, TRUE)
ON CONFLICT (id) DO NOTHING;

-- 7.3 抽样单示例
INSERT INTO template_examples (id, template_id, example_input, example_output, description, sort_order, is_active) VALUES
    ('c0000000-0000-0000-0000-000000000003',
     'b0000000-0000-0000-0000-000000000003', 
     '产品质量监督抽查抽样单...任务来源：西安市市场监督管理局...抽查类别：产品质量监督抽查...生产企业：宁波公牛低压电气有限公司...样品名称：小型断路器...规格型号：LB5-63aC20/1P...生产日期/批号：2025-09-24/13200441...备样封存地点：抽查专用盒...抽样渠道：销售柜台...抽样单位：西安市产品质量监督检验院...抽样日期：2025年9月24日',
     '{"task_source": "西安市市场监督管理局", "task_category": "产品质量监督抽查", "manufacturer": "宁波公牛低压电气有限公司", "sample_name": "小型断路器", "specification_model": "LB5-63aC20/1P", "production_date_batch": "2025-09-24/13200441", "sample_storage_location": "抽查专用盒", "sampling_channel": "销售柜台", "sampling_unit": "西安市产品质量监督检验院", "sampling_date": "2025-09-24", "sampled_province": "陕西省", "sampled_city": "西安市"}',
     '抽样单标准示例',
     1, TRUE)
ON CONFLICT (id) DO NOTHING;


-- ############################################################
-- PART 9: 飞书推送配置（统一使用模板配置）
-- ############################################################

-- 9.1 抽样单 → 质量管理中心多维表格
UPDATE document_templates
SET feishu_bitable_token = 'WNYMbxfiIaY7rasaO44caKxznxd',
    feishu_table_id = 'tblV1HgMnDRQH0eg'
WHERE id = 'b0000000-0000-0000-0000-000000000003';

-- 9.2 检测报告 → 质量管理中心多维表格
UPDATE document_templates
SET feishu_bitable_token = 'WNYMbxfiIaY7rasaO44caKxznxd',
    feishu_table_id = 'tblqjX6PRcLMFhUU'
WHERE id = 'b0000000-0000-0000-0000-000000000001';

-- 快递单（express）当前无飞书推送需求，feishu_bitable_token / feishu_table_id 保持 NULL。



-- ############################################################
-- 完成
-- ############################################################

SELECT '002_init_data.sql: 租户和模板初始化数据创建完成！' as message;
SELECT '已创建租户: 质量管理中心(quality), 照明事业部(lighting)' as tenants;
SELECT '质量管理中心模板: 检测报告, 快递单, 抽样单' as quality_templates;
