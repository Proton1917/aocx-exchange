# AOCX 研究依据与设计取舍

研究日期：2026-11-23。论文原始实验、仓库文档及本工具实际执行分别登记。本文的设计结论是对这些材料的工程综合。

## 目录

1. 主要文献与采用原则
2. 代码仓库与标准
3. 核心架构选择
4. 自由探索与检查
5. 实现范围与评价

## 1. 主要文献与采用原则

| 原始研究 | 已核对内容 | 对 AOCX 的具体影响 |
|---|---|---|
| BabelTele，Zhu 等，2026 预印本 | 多语言词汇与符号折叠、读者组合、任务保真和额外推理成本 | 采用可插拔语言视图；记录编码器、读者、tokenizer 和任务；底稿保留 |
| LLMLingua-2，ACL Findings 2024 | 蒸馏得到的 token 选择、任务无关抽取式压缩 | 允许独立编码器及原生参数，不把一个压缩算法写死为核心 |
| LongLLMLingua，ACL 2024 | 查询感知压缩、重排、动态预算 | 视图声明查询范围与选择内容；压缩前后评估任务和位置影响 |
| Sufficient Context，ICLR 2025 | 上下文是否足够与模型能否利用它分开评估 | 保存范围和证据；机器引用完整性与读者任务正确率分别报告 |
| Lost in the Middle，TACL 2024 | 相关信息位置改变长上下文任务表现 | 采用短入口、按需展开；测量内容位置，不把档案全文常驻上下文 |
| LongMemEval，ICLR 2025 | 多会话检索、更新、时间推理、未知答案 | 固定修订、保留时间范围和更新关系，加入旧版本/未知答案测试 |
| RECOMP，ICLR 2024 | 抽取/生成压缩与选择性增强，可返回空摘要 | 支持按任务选择和明确的空视图状态 |
| RO-Crate，Data Science 2022 | 用轻量元数据描述研究文件、关系与来源 | 档案明确原件、索引、外部资源及版本，证据随成果可定位 |
| The Information Bottleneck Method，Tishby 等 | 为目标变量保留相关信息的压缩观点 | 把压缩目标绑定到接收任务；不以最短文本作为唯一目标 |
| Beyond Message Passing，2026 预印本 | 区分运输、语法与语义协调 | MCP、交换核心、领域 profile 与编码层各自演进 |

BabelTele 的论文将其定位为经验性表示范式。文中 99.5% 指所报告下游问答表现的保留指标；原文复原、保护字段一致和读者任务表现各有自己的检验。本实现采用这种区分，具体实验数字归原作者。

### 文献

1. Zhu et al. Large Language Models Do Not Always Need Readable Language. https://arxiv.org/html/2606.19857v1
2. Pan et al. LLMLingua-2: Data Distillation for Efficient and Faithful Task-Agnostic Prompt Compression. https://aclanthology.org/2024.findings-acl.57/
3. Jiang et al. LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression. https://aclanthology.org/2024.acl-long.91/
4. Joren et al. Sufficient Context: A New Lens on Retrieval Augmented Generation Systems. https://research.google/pubs/sufficient-context-a-new-lens-on-retrieval-augmented-generation-systems-2/
5. Liu et al. Lost in the Middle: How Language Models Use Long Contexts. https://aclanthology.org/2024.tacl-1.9/
6. Wu et al. LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory. https://arxiv.org/abs/2410.10813
7. Xu, Shi, Choi. RECOMP: Improving Retrieval-Augmented LMs with Context Compression and Selective Augmentation. https://proceedings.iclr.cc/paper_files/paper/2024/hash/bda88ed2892f5e61c9a9bf215c566913-Abstract-Conference.html
8. Soiland-Reyes et al. Packaging Research Artefacts with RO-Crate. https://arxiv.org/abs/2108.06503 ; https://doi.org/10.3233/DS-210053
9. Tishby, Pereira, Bialek. The Information Bottleneck Method. https://arxiv.org/abs/physics/0004057
10. Yuan et al. Beyond Message Passing: A Semantic View of Agent Communication Protocols. https://arxiv.org/abs/2604.02369v3

## 2. 代码仓库与标准

### AOCI

https://github.com/aoci-spec/aoci-code

读取固定提交 `3d8e4b0048b7ae93d671ffae39db73a44db434d3` 的公开规范、实际认知资产及解析器。AOCI 的功能职责、精选关系、接口与约束分别映射；原生标签字典、资源身份与交付机制保留。适配器自行实现，不复制原仓库实现代码。

### 压缩与评估实现

- Microsoft LLMLingua：https://github.com/microsoft/LLMLingua 。参考其模型、rate、query 与 forced-token 等可配置接口；本版提供编码器契约，具体模型由宿主调用。
- LongMemEval：https://github.com/xiaowu0162/LongMemEval 。参考任务类别、支持会话与时间字段；实际采用时固定数据版本。
- Lost in the Middle：https://github.com/nelson-liu/lost-in-the-middle 。参考内容位置与长度的对照实验。
- RECOMP：https://github.com/carriex/recomp 。参考抽取与生成两种方式，以及选择性增强。
- TOON：https://github.com/toon-format/toon 与 https://github.com/toon-format/spec 。可选确定性 JSON 编码；其优势依数据形状而变，采用时运行值级往返测试。
- BabelTele 社区项目：https://github.com/Minglink/BabelTele-Whitepaper 与 https://github.com/lukaszgryglicki/babeltele 。它们的规范、实现和结果分别归各自作者。本规范保留原论文与社区实现的不同来源。

### 基础标准

- MCP 工具规范：https://modelcontextprotocol.io/specification/2025-11-25/server/tools 。采用现有工具/资源及结构化结果承载，不改变原工具 schema。
- JSON Schema 2020-12：https://json-schema.org/draft/2020-12/json-schema-core 。提供可选结构校验描述，领域数据保持可扩展。
- W3C PROV-O：https://www.w3.org/TR/prov-o/ 。借鉴对象、活动和责任主体的来源区分；AOCX 核心为轻量对象图，当前实现不声称已提供完整 PROV-O 导出。
- JSON-LD 1.1：https://www.w3.org/TR/json-ld11/ 。借鉴限定身份与词汇扩展，未来可由 profile 映射到链接数据。
- RO-Crate：https://www.researchobject.org/ro-crate/specification/1.1/introduction.html 。借鉴资源与上下文实体共同描述。当前 JSONL 封装自成契约，RO-Crate 导出可单独注册。

## 3. 核心架构选择

选择可独立调用的本地库/CLI作为稳定实现；薄 Skill 提供渐进披露入口；现有 AOCI MCP 继续提供软件认知服务。格式核心独立于模型厂商和传输协议。

将正文置于自由 text/body，把可自动识别的身份、版本、依赖、来源与条件置于少量结构字段。这样模型可以自由提出概念，而接收方可以确定每个概念对应哪个版本与范围。

选择 JSONL 作为基线，另提供确定性表格编码与可选语义视图。每种编码有独立的 profile/version。相同快照可为数学审查、代码编辑或教材编写生成不同视图。

源文件精确保留、规范化字段投影与语义压缩分别给出验证范围。修改后的原生导出继续接受原系统规则。AOCI 的 R 关联不会被提升为自动证明前提；GBCX 的条件证明不会被提升为已经消除条件的结论。

## 4. 自由探索与检查

最小记录只需要身份、修订、种类和自由文本。思维导图、片段、反例候选、未完成计算及非标准符号均可表达。领域约束在其声明适用的对象上启用。

硬检查解决具体传输缺陷，例如引用不存在、同一修订有两份不同内容、摘要对应错误来源、单位锚点改变或条件引用丢失。思路是否有启发性、证明是否成立由领域评估承担。

采用开放类型和可选 profile，允许一份档案混合探索记录与正式结果。共享稳定的最小规则有助于逐步把新想法转成可测试对象。

## 5. 实现与评价范围

本地已经实现源格式导入、存储验证、源字节恢复、表格视图、条件闭包、冲突检查与语言视图保护字段检查。基础操作通过 Python 标准库运行；JSON Schema 独立检验使用 jsonschema。

本次没有训练或运行 BabelTele/LLMLingua 模型，也没有把论文实验当作本工具的模型性能。正式启用语义压缩时按 validation.md 对实际读者、模型、tokenizer 和任务运行独立评价。
