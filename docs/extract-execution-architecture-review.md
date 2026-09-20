# Extract 执行架构评审稿（供 GPT-6 Pro 评审）

## 目的

NeoFlow 2.0 的 Extract 轮即将开始。评审稿聚焦**执行层架构**：给定已冻结的产品/契约决策，请给出实现架构建议，并指出过度设计风险。请只针对下面列出的开放问题给意见，不要重新讨论已冻结的决策。

## 背景

NeoFlow 2.0 是企业文档能力平台（Parse / Extract / Classify / Split），控制台是配置与验证面，对外消费走 API/中台。Parse 轮已完成：MinerU 托管 API 解析，产出统一 `ParseResult` 契约（文档→页→块，块类型含 text/title/table/figure/formula 等，带 bbox/reading_order，附每页 markdown 与全文 markdown），结果持久化并可按文档/任务读取。

现有抽取实现（将被本轮重做执行层，但保留其引擎模块作为起点）：

- `agents/workflow.process_with_configuration`：取解析结果（缺失时可自动补解析 `ensure_parse_result`），拼 prompt，调一次 LLM。
- `services/parse_extraction.run_parse_extraction`：把**整文档 markdown** 一次性交给 LLM，JSON 解析后返回结果。
- LLM 客户端：LangChain `ChatOpenAI`（OpenAI 兼容，`response_format=json_object`，默认 DeepSeek 模型，3 次重试）。
- prompt 生成：硬编码模板 + 扁平字段表（field_key/label/type + description）。
- 结果：单行 Result（`data` = 字段值 map）。

## 已冻结的决策（不要再讨论）

1. **Schema = JSON Schema 子集原生契约**（object 根节点，嵌套对象/数组，字段 `description` 即引导语），配置里存 `data_schema`；UI 编辑走 Raw JSON（Builder 后置）。
2. **抽取目标 target = `per_doc` / `per_page` / `per_table_row`**，作为配置项随配置冻结；结果形状随之变化（单对象 / 页数组 / 实体数组）。
3. **配置模型**：Extract 保留 Configuration（草稿/发布/Revision）；草稿可在 Playground 运行，运行时把 schema/target/参数**冻结快照到 Job**（不产生 Revision）；正式运行 pin 已发布 Revision。
4. **执行语义**：per-file Job；抽取前**持久化 Parse Result 绑定**（重试沿用绑定，不读最新解析）；认领感知 + 原子交卷（沿用 Parse 的 claim/commit 模式）。
5. **不做**：审核、Excel/Feishu 推送、citations/confidence、幂等受理与租户配额（留给对外接口轮）、嵌套 Builder、多模型档位（tier）。
6. **结果契约**：`data` 直接存 JSON Schema 形状（对象或数组）；engine 记录 schema/target/模型等元信息；结果只读展示（JSON 树），无审核面板。
7. **UI 信息架构**：Build（选配置 + 从本机上传/选择文档 + 草稿 schema 只读预览 + Run）/ Results（JSON 树 + 复制/下载）/ History（Job 列表）。上传只负责文档接入，不要求先选择模板；模板由管理员配置和发布。

## 约束与环境

- Parse 产物可用：页级 markdown + 块级结构（表格是块，含 `table_html`）；文档可能很长（数十到数百页），也有单页小文件。
- Worker：独立进程，一次认领一个 Job；LLM 供应商可换（OpenAI 兼容协议），本轮只用单一模型。
- 目标：可调试、可测试、失败可解释；优先最简单可行方案，避免为未来多模型/多供应商提前造抽象层。

## 开放问题（请逐条给具体建议）

1. **Schema→prompt 与结构化输出**：如何从 JSON Schema + description 生成 prompt？如何约束/校验 LLM 输出（类型、required、null、数组 item）？是否需要"校验失败 → 带错误重试"的修复环，还是 JSON mode + 后处理归一化就够？

2. **长文档策略**：`per_doc` 是否必须整文档单次调用？还是按页/块分块抽取后合并（map-reduce / refine）？token 预算、上下文截断、跨页字段（如合同起止日期分布在不同页）如何权衡？`per_page` 天然按页调用时，页间字段一致性（如重复表头）怎么处理？

3. **`per_table_row` 的实体识别**：用 ParseResult 的表格块做确定性切分（按行），还是 LLM 驱动实体识别（列表/小节也可能承载实体）？混合方案如何划界？实体顺序与边界如何校验？

4. **Workflow 架构形态**：确定性流水线（schema→prompt→调用→校验→修复）还是 LLM 工具循环（给模型解析产物检索工具，自主定位）？考虑可测试性、可观测性与成本，推荐哪种，模块边界怎么切？

5. **失败与部分成功语义**：`per_page` 中部分页失败、`per_table_row` 中部分行失败，应整单失败还是产出带缺失标记的部分结果？重试粒度（整单/单页/单行）与上限？

6. **本轮不该造什么**：请明确列出在这个决策集下**不需要**的抽象或机制（例如：模型路由层、缓存层、schema 编译器、agent 框架等），防止过度设计。

## 期望输出

- 每条问题给出明确推荐 + 理由 + 主要取舍；
- 给出一张执行层模块/数据流草图（文字描述即可）；
- 列出你建议先写测试的 3-5 个关键行为；
- 如有与上述冻结决策冲突之处，直接指出，但不要臆造未给出的需求。
