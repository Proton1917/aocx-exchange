# AOCX 兼容与语言 profile

## 兼容层级

分别声明原始字节保存、原字段保留、指定语义投影、修改后原生导出四项能力。前两项按字节或 JSON 值检查；投影列明映射范围；原生导出服从原系统验证。

初始实现提供原档案精确恢复和规范化投影。restore 恢复导入时的原 ZIP；目录导入恢复各文件原字节。编辑投影后的原生重新生成属于单独能力，本版导入器将修改保留在新档案中。

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

真实上游 Root/Meta/Code 三资产投影为 497 条记录、1013 条关联。5 个 R 目标在输入中缺少对应对象，原字符串全部保留。源路径、哈希和范围见 assets/sources。适配器是根据公开契约独立编写的实现。

公开规范：

- https://github.com/aoci-spec/aoci-code/blob/3d8e4b0048b7ae93d671ffae39db73a44db434d3/spec/public/aoci-index-format-v1.txt
- https://github.com/aoci-spec/aoci-code/blob/3d8e4b0048b7ae93d671ffae39db73a44db434d3/spec/public/aoci-cognition-volumes-v1.txt
- https://github.com/aoci-spec/aoci-code/blob/3d8e4b0048b7ae93d671ffae39db73a44db434d3/spec/public/aoci-object-fras-v2.txt

## GBCX/1

六类主记录投影为 claim、method、question/task、source、term 和源码实体。完整原 JSON 保存在 body，数学文字、公式、量词、范围和假设保持原意。

written_proof/conditional → knowledge:derived；source_inspected → reported；数值记录 → observed。原验证描述完整保存。旧 dependencies.json 的前提 → 使用者转为使用者 → 前提。condition_bearing_dependencies 同时生成固定修订的引用条件；缺少表述的条件命题保留明确待补条件。方法 claim_ids 作为关联。

真实交接包的 422 条主记录全部保留原 JSON 值，生成 320 条可解析关系。附属索引、证明、未知资料和注释随原档案保存。主记录投影与附属资源字节保存分别登记。

## BabelTele 语言视图

babeltele-view/1 是 AOCX 定义的承载 profile。论文中的 BabelTele 生成方式作为编码器接入，措辞随模型、任务与参数变化。

视图记录源文件摘要、固定修订引用、任务、压缩模型和提示词摘要、读者模型/tokenizer、压缩文本、保护字段和评估证据。

格式字段：format=AOCX-VIEW、version=1.0、codec=babeltele-view/1、namespace、source_records_sha256、source_relations_sha256、task、producer{model,prompt_sha256}、consumer{model,tokenizer}、entries[{ref,text,protected}]、evaluation{status,report?}。命名空间、正文摘要与关系摘要共同绑定来源，关系改变也使旧视图失效。

protected 保留原记录除 text/body/extensions 外的字段。重要数量、单位、方程、量词和例外先写入 anchors、conditions 或 scope；保留源记录以便回取。引用条件需要进入选择闭包。

check-view 校验源版本、保护字段和引用范围。评估状态 passed 需要可定位的报告，程序分别输出结构检查与评估声明。报告应列出问题、答案、模型版本、评分方法和运行结果。

附带手写示例与检查器。模型生成由宿主编码器完成，参数和任务范围随视图登记；论文实验结果保留其作者与测试范围。

## 其他编码与新领域

JSONL 与 table-jsonl/1 是可执行基线。TOON 可另行注册为确定性编码器，按解码后的 JSON 值验收。LLMLingua-2、LongLLMLingua 和自定义摘要器作为语义编码器，另外记录任务表现。本版提供这些扩展的契约，具体模型/TOON 实现由宿主选择。

新领域可以先声明种类和字段，例如文档 learning_objective、实验 unit/sample_size、代码 interface；需要更强保证时再注册 schema 与检查函数。自由表达与逐步结构化可并存。
