# AOCX 兼容与语言 profile

本文规定可执行编码、原格式适配和任务条件语言视图的能力范围。记录与表示字段见[核心规范](specification.md)，测试与测量口径见[验证规范](validation.md)。

## 可执行表示

`compile` 在同一 `AOCX-REP` 封装上比较已实现的 codec。保全契约固定目标后，每个候选都完成真实解码和类型、值比较。

| codec / 接口 | 表示方法 | 验收与使用范围 |
| --- | --- | --- |
| `aocx-expr/1` | 用 `Rep`、`Context`、`Record`、`Relation`、`Ref`、`Logic` 因子化重复结构与显式逻辑 | 默认编译候选，恢复完整封装 |
| `aocx-expr-dict/1` | 在表达式上增加 wire 内共享字符串词典 | 默认编译候选，词典成本纳入测量 |
| `json/1` | 完整封装的严格 JSON | 显式候选和比较基线 |
| `table-jsonl/1` | 表头与位置行 | `capsule` / `parse_capsule` 的既有兼容格式 |
| `babeltele-view/1` | 指定任务与读者的语言视图 | 结构、证据绑定、实际评估分别验收 |

`CodecRegistry` 通过 `Codec(id, encode, decode)` 注册宿主实现。编码器返回带相应 `AOCX/1 <codec-id>` 首行的字节，decoder 恢复封装。通过 `--reader` 或 Python API 提供的能力声明限制可选 codec 与必需 profile。候选长度比较始终发生在保全检查之后。

## 兼容层级

分别声明原始字节保存、原字段保留、指定语义投影、修改后原生导出四项能力。前两项按字节或 JSON 值检查；投影列明映射范围；原生导出服从原系统验证。

导入器提供原档案精确恢复和规范化投影。`restore` 恢复导入时的原 ZIP；目录导入恢复各文件原字节。编辑投影后的原生重新生成属于单独能力，导入器将修改保留在新 AOCX 档案中。`compile --mode exact` 恢复的范围是该档案的上下文值，附件与原件字节随原档案交付。

## AOCI-CODE

核对版本：aoci-spec/aoci-code，提交 3d8e4b0048b7ae93d671ffae39db73a44db434d3，README 标记 v0.2.0-rc3。公开契约为 Cognition Volumes v1、Object FRAS v2，兼有 Legacy 读取。

| 原内容 | 投影 |
|---|---|
| Code/Database 身份 | 稳定 ID，保留原生身份 |
| F：功能职责 | text 与完整原字段 |
| R：精选强关联 | relates_to，未解析者保留原字符串和提示 |
| A：稳定接口契约 | body 内原字段 |
| S：非显然约束 | body 内约束 |
| Tag / Meta | 原标签、所属卷和字典绑定 |
| 原条目 / 未知段 | raw_entry、原始文本和原档案 |

S 与工作状态、R 与证明前提分别保存。重要度保留原生含义。适配器支持已核对卷结构及清晰的旧根路径表达，歧义内容保存原文并提示。

固定上游样本的历史执行记录包含 497 条投影记录、1013 条关联；其中 5 个 R 目标在输入中缺少对应对象，原字符串全部保留。样本身份见 [`aoci_sources.json`](../assets/sources/aoci_sources.json)，当次结果见 [`aoci_projection.json`](../assets/validation/aoci_projection.json) 与 [`aoci_protected_handoff.json`](../assets/validation/aoci_protected_handoff.json)。适配器按公开契约实现，仓库索引维护继续遵循[原生 AOCI 流程](mcp-binding.md)。

公开规范：

- https://github.com/aoci-spec/aoci-code/blob/3d8e4b0048b7ae93d671ffae39db73a44db434d3/spec/public/aoci-index-format-v1.txt
- https://github.com/aoci-spec/aoci-code/blob/3d8e4b0048b7ae93d671ffae39db73a44db434d3/spec/public/aoci-cognition-volumes-v1.txt
- https://github.com/aoci-spec/aoci-code/blob/3d8e4b0048b7ae93d671ffae39db73a44db434d3/spec/public/aoci-object-fras-v2.txt

## GBCX/1

六类主记录投影为 claim、method、question/task、source、term 和源码实体。完整原 JSON 保存在 body，数学文字、公式、量词、范围和假设保持原意。

written_proof/conditional → knowledge:derived；source_inspected → reported；数值记录 → observed。原验证描述完整保存。旧 dependencies.json 的前提 → 使用者转为使用者 → 前提。condition_bearing_dependencies 同时生成固定修订的引用条件；缺少表述的条件命题保留明确待补条件。方法 claim_ids 作为关联。

固定交接包的历史执行记录覆盖 422 条主记录和 320 条关系，记录了原 JSON 值保留与原件恢复，见 [`gbcx_roundtrip.json`](../assets/validation/gbcx_roundtrip.json)。附属索引、证明、未知资料和注释随原档案保存。主记录投影与附属资源字节保存分别登记。

## BabelTele 语言视图

`babeltele-view/1` 是 AOCX 定义的任务条件语言视图 profile。BabelTele 或其他宿主语言编码器生成正文，视图随具体模型、任务与参数登记。对应研究来源见[研究记录](research.md)。

视图记录源文件摘要、固定修订引用、任务、压缩模型和提示词摘要、读者模型/tokenizer、压缩文本、保护字段和评估证据。

格式字段：format=AOCX-VIEW、version=1.0、codec=babeltele-view/1、namespace、source_records_sha256、source_relations_sha256、task、producer{model,prompt_sha256}、consumer{model,tokenizer}、entries[{ref,text,protected}]、evaluation{status,report?}。命名空间、正文摘要与关系摘要共同绑定来源，关系改变也使旧视图失效。

`protected` 保留原记录除 `text`、`body`、`extensions` 外的全部字段，包含显式 `logic`。重要数量、单位、方程、量词和例外可以写入 `anchors`、`conditions` 或 `scope`；保留源记录以便回取。引用条件需要进入选择闭包。

`check-view` 检查源版本、保护字段和引用范围。`evaluation.status=passed` 要求 `evaluation.report` 指向档案内已登记摘要的报告资源。强绑定报告格式为：

```json
{"format":"AOCX-EVALUATION","version":"1.0","view_sha256":"<SHA256>","source_snapshot_sha256":"<SHA256>"}
```

报告可附加问题、答案、模型版本、评分方法、阈值和运行结果。`source_snapshot_sha256` 绑定完整源上下文快照；`view_sha256` 由 `view_digest(view)` 计算，输入为去掉顶层 `evaluation` 后的全部视图字段。因此压缩正文、任务、读者、生产者、来源摘要和保护字段都进入绑定。排除评估引用避免报告与视图相互计算摘要。

摘要序列化使用 UTF-8、对象键排序、紧凑 JSON 分隔符、直接保留 Unicode、有限 JSON 数值，末尾无换行；具体算法为 `SHA256(_content(value).encode("utf-8"))`。构造报告时先完成视图正文和读者任务声明，再计算两个摘要，最后将报告作为档案资源登记并设置 `evaluation.report`。

| 检查状态 | 含义 |
| --- | --- |
| `structural` | 来源、引用、保护字段和报告资源等结构契约的检查结果 |
| `evidence_bound` | 评估报告绑定当前视图内容和源快照 |
| `semantic_evaluation_verified` | 宿主评估器已读取绑定证据并返回严格布尔值 `True` |
| `eligible` | 声明通过、证据绑定通过且宿主评估器实际确认通过 |

Python API `check_view(path, view, evaluator=None)` 允许宿主注册评估器。声明 `passed` 且绑定通过后，评估器收到 `report`、`view`、`source` 的独立副本，按所声明任务判定结果。CLI 执行结构与绑定检查，保留实际评估尚未执行的状态。旧报告作为宿主历史声明保留，并附加缺少强绑定的提示；声明新报告格式后，摘要不匹配进入失败结果。

附带手写示例与检查器。模型生成由宿主编码器完成，参数和任务范围随视图登记；论文实验结果保留其作者与测试范围。

## 其他编码与新领域

外部确定性编码可通过实际注册的 encoder/decoder 接入相同候选验收流程，恢复完整封装后参与成本比较。任务条件摘要器通过语言视图 profile 接入，记录其任务表现与适用读者。具体外部编码和模型实现由宿主提供。

新领域可以先声明种类和字段，例如文档 learning_objective、实验 unit/sample_size、代码 interface；需要更强保证时再注册 schema 与检查函数。自由表达与逐步结构化可并存。
