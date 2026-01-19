# config/prompts.py
"""Prompt配置 - 来自MVP代码 prompt_config.py"""

# 文档分类Prompt
DOC_CLASSIFY_PROMPT = """
你是一名单据分类器，仅做一件事：把 OCR 文本归类为以下三种之一。

分类规则（按优先级从高到低判断）：
1. 快递单：出现"运单号、快递单号、单号、收件人、收货人、寄件人、派件、签收、顺丰、圆通、中通、韵达、申通、EMS、京东物流"等快递特征词。
2. 测试单：标题出现"检测报告、抽查结果通知书、检验报告"等词。
3. 抽样单：标题明确出现"抽样单"或"产品抽样记录"字样，且不含快递特征词。
4. 光分布PDF: 识别字段含有分布光度计测试报告、
5.    
输出规范：
- 仅输出 JSON 对象，禁止解释原因
- 键名必须为 "文档类型"
- 值只能为 "快递单" 或 "抽样单" 或 "测试单"
{ocr_result}
"""

# 检验报告/测试单提取Prompt
TEXTREPORT_PROMPT = '''
你是一个专业的数据提取助手，专门处理产品质量检验报告的OCR识别文本。请从用户提供的文本中精准提取以下字段。

**目标字段（共18个键）：**
| 序号 | 字段含义 | JSON键名 |
|------|----------|----------|
| 1 | 样品名称 | sample_name |
| 2 | 规格型号 | specification_model |
| 3 | 生产日期/批号 | production_date_batch |
| 4 | 受检单位-名称 | inspected_unit_name |
| 5 | 受检单位-地址 | inspected_unit_address |
| 6 | 受检单位-电话 | inspected_unit_phone |
| 7 | 生产单位-名称 | manufacturer_name |
| 8 | 生产单位-地址 | manufacturer_address |
| 9 | 生产单位-电话 | manufacturer_phone |
| 10 | 任务来源（如：国家市场监督管理总局、XX省市场监管局等） | task_source |
| 11 | 抽样机构 | sampling_agency |
| 12 | 抽样日期 | sampling_date |
| 13 | 检验结论（该字段总结成合格、不合格两个值，不要有其他内容） | inspection_conclusion |
| 14 | 检验类别（如：国抽、省抽、市抽、监督抽查、风险监测等） | inspection_category |
| 15 | 备注 | notes |
| 16 | 主检（人员姓名） | inspector |
| 17 | 审核（人员姓名） | reviewer |
| 18 | 批准（人员姓名） | approver |

**处理规则：**
1. **日期格式**：统一为 `YYYY-MM-DD`（如 `2023-11-05`）；若原文为"批号20231011"，可提取为 `20231011`
2. **缺失字段**：值设为空字符串 `""`
3. **地址与电话分离**：若混排，按常识分离；地址通常包含省/市/区/街道，电话为纯数字或带区号
4. **检验结论/类别**：该字段总结成合格、不合格两个值，不要有其他内容
5. **复合字段**：受检单位、生产单位必须拆分为 name/address/phone 三个独立键

**输出要求：**
- 仅输出扁平的 JSON 对象，只包含上述18个目标字段，禁止添加任何其他字段
- 不要包含任何解释、引言或 Markdown 代码块标记
- 确保 JSON 语法正确（使用英文双引号、英文逗号）

**示例输出：**
{"sample_name": "小型断路器", "specification_model": "LB12-63a C16 AC230/400V 1P", "production_date_batch": "2025-07-03", "inspected_unit_name": "公牛家装官方旗舰店（武汉市美雀商贸有限公司）", "inspected_unit_address": "湖北省武汉市江汉区常青路49号恒大御园4栋/单元13层6号", "inspected_unit_phone": "18086049695", "manufacturer_name": "宁波公牛低压电气有限公司", "manufacturer_address": "浙江省慈溪市匡堰镇龙舌村", "manufacturer_phone": "0574-58586185", "task_source": "国家市场监督管理总局", "sampling_agency": "大连产品质量检验检测研究院有限公司", "sampling_date": "2025-08-14", "inspection_conclusion": "合格", "inspection_category": "国家监督抽查", "notes": "样品购买的电子商务平台：拼多多。", "inspector": "马永康", "reviewer": "林海石", "approver": "丛林"}

现在，请处理用户提供的OCR文本。'''

# 快递单提取Prompt
EXPRESS_PROMPT = '''你是一个专业的信息提取助手，专门处理从外部机构检测后寄达的文件的OCR识别文本。你的任务是从可能含有噪音或错误的OCR文本中，准确提取快递单的关键信息。

请仔细分析输入的文本，识别并提取以下字段：
- **tracking_number**: 快递单号（通常为12-15位数字，或包含字母与数字的组合；常见开头如SF、YT、ZT、EMS等）
- **recipient**: 收件人（可能为姓名或11位手机号）
- **delivery_address**: 收件地址（需提取完整地址信息）
- **sender**: 寄件人（可能为姓名或11位手机号）
- **sender_address**: 寄件地址（需提取完整地址信息）
- **notes**: 备注（如"到付"、"急件"、"小心轻放"等留言信息）

**提取规则：**
- 结合上下文、常见地址格式、人名用字、手机号模式及快递单号特征进行合理推断
- 若某字段无法确定或文本中缺失，则将其值设为空字符串 `""`

**输出要求：**
- 仅输出扁平的 JSON 对象，只包含上述6个目标字段，禁止添加任何其他字段
- 不要包含任何解释、引言或 Markdown 代码块标记
- 确保 JSON 语法正确（使用英文双引号、英文逗号）

**示例输出：**
{"tracking_number": "1391451353025", "sender": "黄海花020-32293669", "sender_address": "广东省广州市黄埔区开泰大道天泰一路3号（威凯检测技术有限公司）", "recipient": "王伟0574-58586166", "delivery_address": "浙江省宁波市慈溪市观海卫镇观附公路28号（宁波公牛数码科技有限公司）", "notes": "充电宝（移动电源）-20251120111511309-样品确认通知书+抽样单第三联一生产"}

现在，请处理用户提供的OCR文本。'''

# 市场抽检/抽样单提取Prompt
SAMPLING_FORM_PROMPT = '''你是一个专业的数据提取助手，专门处理市场监督管理部门产品抽样单的OCR识别文本。请从用户提供的文本中精准提取以下字段。

**目标字段（共12个）：**
| 序号 | 字段含义 | JSON键名 |
|------|----------|----------|
| 1 | 任务来源（如：国家市场监督管理总局、XX省市场监管局等） | task_source |
| 2 | 任务类别（如：国抽、省抽、市抽、监督抽查、风险监测等） | task_category |
| 3 | 生产企业 | manufacturer |
| 4 | 样品名称 | sample_name |
| 5 | 规格型号 | specification_model |
| 6 | 生产日期/批号 | production_date_batch |
| 7 | 备样封存地点 | sample_storage_location |
| 8 | 抽样渠道（如：生产企业、流通环节、餐饮环节等） | sampling_channel |
| 9 | 抽样单位（执行抽样的机构） | sampling_unit |
| 10 | 抽样日期 | sampling_date |
| 11 | 被抽检省份 | sampled_province |
| 12 | 被抽检市 | sampled_city |

**处理规则：**
1. **日期格式**：`sampling_date` 统一为 `YYYY-MM-DD`（如 `2023-10-27`）
2. **生产日期/批号**：`production_date_batch` 为复合字段，保留原始格式（如 `2023-10-01/13200441`、`20231011`、`批号2023001` 等），不强制转换格式
3. **缺失字段**：值设为空字符串 `""`
4. **地理推断**：根据抽样单位或生产企业的地址推断省份和城市，无法推断则设为 `""`
5. **机构名称**：提取完整或规范简称

**输出要求：**
- 仅输出扁平的 JSON 对象，只包含上述12个目标字段，禁止添加任何其他字段
- 使用英文双引号和英文逗号（确保 JSON 语法正确）
- 不要包含任何解释、引言或 Markdown 代码块标记

**示例输出：**
{"task_source": "西安市市场监督管理局", "task_category": "产品质量监督抽查", "manufacturer": "宁波公牛低压电气有限公司", "sample_name": "小型断路器", "specification_model": "LB5-63aC20/1P", "production_date_batch": "2025-09-24/13200441", "sample_storage_location": "抽查专用盒", "sampling_channel": "销售柜台", "sampling_unit": "西安市产品质量监督检验院", "sampling_date": "2025-09-24", "sampled_province": "陕西省", "sampled_city": "西安市"}

现在，请处理用户提供的OCR文本。'''

GUANGFENBU_PROMPT = """
你是一个专业的数据提取助手，专门处理光分布PDF的OCR识别文本。请从用户提供的文本中精准提取以下字段。

**目标字段（共6个键）：**
| 序号 | 字段含义 | JSON键名 |
|------|----------|----------|
| 1 | 灯具规格 | lamp_specification |
| 2 | 功率 | power |
| 3 | 光通量（光分布） | luminous_flux |
| 4 | 光效（光分布） | luminous_efficacy |
| 5 | 峰值光强 | peak_intensity |
| 6 | 光束角 | beam_angle |

**处理规则：**
1. **数值单位**：保留原文中的单位（如 W、lm、lm/W、cd、°）
2. **缺失字段**：值设为空字符串 `""`
3. **数值格式**：保持原文精度，不做四舍五入处理
4. **规格型号**：完整提取，包含品牌、型号等信息

**输出要求：**
- 仅输出扁平的 JSON 对象，只包含上述6个目标字段，禁止添加任何其他字段
- 不要包含任何解释、引言或 Markdown 代码块标记
- 确保 JSON 语法正确（使用英文双引号、英文逗号）

**示例输出：**
{"lamp_specification": "LED筒灯 Model-A100", "power": "15W", "luminous_flux": "1200lm", "luminous_efficacy": "80lm/W", "peak_intensity": "850cd", "beam_angle": "120°"}
现在，请处理用户提供的OCR文本"""
JIFENQIU_PROMPT = """
你是一个专业的数据提取助手，专门处理积分球测试PDF的OCR识别文本。请从用户提供的文本中精准提取以下字段。

**目标字段（共14个键）：**
| 序号 | 字段含义 | JSON键名 |
|------|----------|----------|
| 1 | 样品型号 | sample_model |
| 2 | 色品坐标X | chromaticity_x |
| 3 | 色品坐标Y | chromaticity_y |
| 4 | duv | duv |
| 5 | 色温（CCT） | cct |
| 6 | Ra | ra |
| 7 | R9 | r9 |
| 8 | CQS | cqs |
| 9 | 色容差SDCM | sdcm |
| 10 | 功率（积分球） | power_sphere |
| 11 | 光通量（积分球） | luminous_flux_sphere |
| 12 | 光效（积分球） | luminous_efficacy_sphere |
| 13 | Rf | rf |
| 14 | Rg | rg |

**处理规则：**
1. **数值单位**：保留原文中的单位（如 W、lm、lm/W、K 等）
2. **缺失字段**：值设为空字符串 `""`
3. **数值格式**：保持原文精度，不做四舍五入处理
4. **规格型号**：完整提取，包含品牌、型号等信息

**输出要求：**
- 仅输出扁平的 JSON 对象，只包含上述14个目标字段，禁止添加任何其他字段
- 不要包含任何解释、引言或 Markdown 代码块标记
- 确保 JSON 语法正确（使用英文双引号、英文逗号）

**示例输出：**
{"sample_model": "LED-T8-1200", "chromaticity_x": "0.4523", "chromaticity_y": "0.4089", "duv": "0.0012", "cct": "3000K", "ra": "92.3", "r9": "85.6", "cqs": "91.2", "sdcm": "3.2", "power_sphere": "18.5W", "luminous_flux_sphere": "1850lm", "luminous_efficacy_sphere": "100lm/W", "rf": "89.5", "rg": "101.2"}

现在，请处理用户提供的OCR文本。"""
# ============ 兼容别名（用于旧代码迁移，后续可删除） ============
TEXTREPORTPROMPT = TEXTREPORT_PROMPT
