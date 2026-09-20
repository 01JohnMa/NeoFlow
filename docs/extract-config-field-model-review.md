# Extract 配置字段模型扩展 + Builder 评审稿（供 GPT 评审）

## 目的

Extract 轮的执行层已落地（ADR-0009 / `docs/extract-execution-architecture-review.md`）。当时冻结的一条是：

> 配置里存 `data_schema`；**UI 编辑走 Raw JSON（Builder 后置）**。

现在要把"后置的 Builder"提上来，并让配置能表达 **enum / 对象数组**，以便把一个真实的「立项基本信息-药物注册类」38 字段契约在 UI 里配置、调整并运行。

**请只针对文末「开放问题」给具体建议**，并重点指出**过度设计风险**。已冻结的执行层语义（claim/commit、Job 快照、Parse 绑定、`per_doc/per_page` target）不在讨论范围。

## 背景（现状）

- 执行器 schema 契约是 **JSON Schema 子集**：`services/extract_schema.py` 白名单 = `type / properties / items / required / enum / description / format / additionalProperties`；`type` 支持 object/array/string/number/integer/boolean/null；`format` 仅 `date`；取值用 `jsonschema` Draft 2020-12 + `FormatChecker` 真校验。
- 抽取消求：`services/extract_prompt.py:build_extract_messages` 把**整份 schema（含 enum/format/description）**塞进 prompt，规则含「不编造 / 可选省略不输出 null / 枚举只能取 enum 值」；`invoke_llm` 仅 `response_format=json_object`（**非** structured output / function calling 强类型）。
- 校验闭环：`extract_service._run_unit` → `strict_json_loads` → `validate_value`；不合规**只修复一次**（`build_repair_messages`），仍不合规则 Job **失败**（`schema_validation_failed`），不落脏数据。组装后还有一次 `validate_output`。
- 配置定义：`services/configuration_service.py:normalize_definition/normalize_field`（保留未知键）；执行 spec `services/extract_service.py:build_execution_spec` 从 definition 取 `target/data_schema/fields`；`_normalize_params` 里 `data_schema` 优先，否则 `fields` 走 `legacy_fields_to_schema`。
- **当前 UI 字段模型只支持 4 种类型**：`api/routes/configurations.py:29` `Literal["text","date","number","boolean"]`；前端 `web/src/types/index.ts:5 FieldType` 同；`AdminFieldsTab.tsx` 只有「文本/日期/数值/布尔」下拉，**无法表达 enum、对象、数组**。
- AI 生成配置向导（`web/src/components/admin/AiTemplateWizard.tsx` + `sdk/`）产出的字段同样是 `text/date/number`（`sdk/models.py:19 DetectedField`），commit 时写 `configuration.name/code/definition.fields`（`sdk/agents/orchestrator.py:18,71,86`）。
- 结果展示：`web/src/pages/ExtractPlayground.tsx:120` 用 `Object.entries` 把返回 JSON **原样渲染**（数据驱动，缺字段即不显示）。

## 训练样本带来的硬需求

资料包 `template/OCR训练-基本信息-药物注册类/` 的契约含 38 字段，其中：

- **enum**：`trial_phase / blinding_method / multisite_flag / insurance_flag / drug_registration_class / dosage_form`（严格命中候选值）；
- **对象数组** `product[]`：`combination_products / control_products`，每行含 `name(必填) / name_en / specification_model / dosage_form(enum) / drug_registration_class(enum)`；
- **date**：`yyyy-MM-dd`；**number**：纯数字；
- **语义**：找不到依据的字段**整段不输出**（省略），不是 null；`string[]` 类型在规则里被提及但契约中未实际使用。

对照样本：案例 4（苹果酸阿莫曲坦片）输出 29/38，示例 2 输出 37/38——**同一契约的稀疏子集**。

## 本次提议（方案 A）

### 1) 统一字段模型（前后端 + SDK 共用）

```
ConfigurationField {
  field_key, field_label,
  field_type: "text" | "date" | "number" | "boolean" | "enum" | "object",
  multiple: boolean,             // true → 该字段是数组（text→[STR]；object→[OBJ]）
  options?: string[],            // 仅 enum
  items?: ConfigurationField[],  // 仅 object 的子字段（限制一层；子字段只允许标量/enum）
  extraction_hint, sort_order, is_required, default_value, source_doc_type
}
```

即 LlamaIndex 风格的「基础类型 + 数组修饰」，而不是独立的 `array` 类型。（备选方案 B：独立 `array` + `items`，JSON Schema 风。）

### 2) 派生 schema

`legacy_fields_to_schema` 扩展（递归）：

- 标量/enum → `{type, format?:"date", enum?:[...]}`，`description = extraction_hint || field_label`
- `object` → `{type:"object", properties, required:[本级 is_required], additionalProperties:false}`
- `multiple:true` → 外层 `{type:"array", items:<上者>}`
- 根节点 `additionalProperties:false`（现状已如此）

### 3) 语义：省略（非 null）

可选字段不进 `required`，也不给 `null` 留位；模型找不到就不输出该 key。与既有 prompt 规则一致。

### 4) UI

- 配置详情页「识别字段」tab：类型下拉 6 种 + 「数组」勾选 + enum 选项编辑器 + object 子字段编辑器；表格类型列显示（如 `[OBJ]`）。
- **Builder / JSON 双视图**：JSON 视图默认只读展示**派生的 schema**（fields 为单一真源），避免 `fields` 与 `data_schema` 双写错位。
- AI 生成配置向导：改为 LlamaIndex 式单视图（上传样例 + 名称/编码 → 解析 → 「从文档草拟字段」→ Builder/JSON 编辑 → 发布），**保留配置名称/code**（现状已保留：`orchestrator.py:86-87`）。

### 5) 结果展示

`ExtractPlayground` 结果区改为**配置驱动**：按所选配置的字段铺骨架，`data[field_key]` 取值，缺的显示「未提取」；对象数组按行展示；保留原 JSON 视图可切换。

### 6) 种子配置

把 38 字段契约转成上述 fields 模型，**直接写库**生成一条 draft 配置（tenant/project 用现有默认）。`is_required` 仅 `product[].name`。

## 与既有决策的关系（关键偏离，请重点评审）

| 既有冻结方向 | 本次提议 |
| --- | --- |
| 配置存 `data_schema`，UI 编辑走 Raw JSON，Builder 后置 | 配置以 **`fields` 为单一真源**，执行时派生 schema；UI 用 Builder（JSON 只读预览） |

即：把"Raw JSON 优先"翻转为"结构化 fields 优先、schema 派生"。理由：UI 要可编辑且不错位；且执行器本就支持 `legacy_fields` 路径。**这是本次最大决策点。**

## 落地清单（文件）

后端：`api/routes/configurations.py`（字段模型）、`services/configuration_service.py`（`FIELD_DEFAULTS`/`normalize_field` 递归）、`services/extract_service.py`（`legacy_fields_to_schema`）、`sdk/models.py`（`DetectedField`）、`sdk/agents/orchestrator.py` + `doc_analyzer_agent.py`（向导透传/草拟）。
前端：`types/index.ts`、`AdminFieldsTab.tsx`、`AdminConfigurationDetail.tsx`、`lib/fieldsToSchema.ts`（新，与后端同构）、`AiTemplateWizard.tsx`、`ExtractPlayground.tsx`。
数据：新增 1 条 configuration。

## 开放问题（请逐条给具体建议）

1. **真源选择**：`fields` 派生 schema（本提议） vs 既有 `data_schema` + Raw JSON。从长期维护/一致性看哪个更优？若要两者共存，如何避免"UI 改了不生效"的错位？是否有必要引入"schema 为真源、fields 为投影"的相反方案？
2. **类型方案**：A（`object` + `multiple`）还是 B（独立 `array` + `items`）？哪个对"数组 of 标量 / 数组 of 对象 / 未来多层嵌套"扩展更干净？
3. **嵌套深度限制为 1 层**是否合理？还是应一开始就允许递归（多花 UI 成本）？
4. **enum 的强校验与 required 的张力**：我们的校验器对 enum/date 真校验、对可选字段要求省略。相比 LlamaIndex 的「全部 required + `anyOf [X,null]` 可空」，哪种更适合"宁缺勿错"？我们是否该支持 `type:["string","null"]` / `anyOf`？
5. **AI 向导输出**：让 LLM 直接产出扩展 `fields`（本提议） vs 产出 JSON Schema 再转 fields？后者的转换在任意 schema 下是否有信息损失？prompt 工程上哪个更稳？
6. **前后端 schema 派生一致性**：靠"同构实现 + 单测对齐"够吗？还是应把派生放到后端接口、前端只读？
7. **种子配置写库**：直接 INSERT vs 迁移脚本 vs UI 导入入口，哪个更可维护/可复现？
8. **结果配置驱动渲染**：缺省字段显示「未提取」是否会掩盖"解析失败/抽取失败"与"确实没有"的差异？展示与导出应如何区分？
9. **过度设计**：本清单里哪些可以砍（例如 JSON 视图、AI 向导改造、object 单值支持）？最小可用集是什么？

## 风险

- `ConfigurationFieldModel` 递归需 `model_rebuild`；`normalize_field` 需递归（否则子字段缺默认键）。
- `DetectedField` 变更会动 confirm-template 契约（前后端 + 测试需同步）。
- SDK 会话存内存（重启丢失）——不在本次范围，但影响 AI 向导体验。
- 历史配置（发票/检测报告，均为 4 类型）必须保持向后兼容。

## 本轮不做

- 多轮对话式精修（"把某字段改成可选""加一个字段"）。
- JSON 视图可编辑（仅只读预览；如需另开）。
- object 嵌套超过一层。
- 审核/人工校对、citations/confidence（沿用既有冻结的"不做"）。
