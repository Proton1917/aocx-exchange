# AOCX/1 核心规范

档案与表示版本：1.0。全称：Agent Object and Context Exchange，智能体对象与上下文交换。本文定义记录图、保全契约、表示封装和内置 wire 格式；[架构说明](architecture.md)给出实现分层，[验证规范](validation.md)给出验收方法。

## 目录

1. 目的与层次
2. 自由内容与最小记录
3. 条件、状态和关系
4. 修订与冲突
5. 档案与资源
6. 上下文与保全契约
7. 表示封装与可逆编码
8. 显式逻辑结构
9. 扩展与协商
10. 兼容接口与实现边界

## 1. 目的与层次

AOCX 在不同 Agent、任务和工具之间传递可继续工作的上下文。编译器以保全契约确定交付对象，先验证每个候选的实际逆变换，再比较完整传输成本。核心提供对象身份、修订、关系、来源和内容容器；领域规则由可独立演进的 profile 描述。代码、数学、文档、数据和自由探索共享这层容器。

四层职责：MCP、文件或函数调用负责运输；AOCX 记录图与保全契约确定目标值；领域 profile 解释专业字段；可执行 codec 编解码目标封装。任务条件语言视图另行登记读者与评估证据。参考实现采用本地命令行及 Python 函数，薄 Skill 按需选择操作。

“必须”用于独立实现之间的可验证契约。自由探索的内容、语言和领域词汇保持开放。机器检查针对声明的契约；领域正确性由相应证据与评估方法处理。

## 2. 自由内容与最小记录

记录是 UTF-8 JSON 对象，至少含四个字符串：

| 字段 | 含义 |
|---|---|
| `id` | 当前 `namespace` 内稳定的对象标识 |
| `rev` | 不可变修订标识；引用指明该值 |
| `kind` | 开放的对象种类，支持领域限定名 |
| `text` | 任意自然语言、公式、伪代码、混合语言或探索性表达 |

```json
{"id":"idea-7","rev":"1","kind":"exploration","text":"尝试把反射相关写成带符号核；先找一个可计算的有限例子。"}
```

常见种类有 entity、claim、task、method、decision、evidence、source、artifact、term、question。新领域可使用 `chemistry/reaction`、`editorial/section` 等名字。核心保留未知种类与未知字段。

可选字段：`body` 保存领域结构；`state` 保存状态；`conditions` 保存条件；`scope` 保存范围和量词；`provenance` 保存来源；`anchors` 保存需要逐值保留的信息；`logic` 保存显式逻辑 AST；`extensions` 保存扩展元数据。原始数据与精确编码保留这些值；投影必须声明省略范围。自由文本与结构字段可以同时使用。

JSON 对象的成员名必须唯一，数值必须有限。跨语言精确数值宜使用十进制字符串或表达式对象，数量同时记录单位。缺失字段、显式 null、布尔值与数值分别保留。数组顺序属于数据值，对象成员顺序由序列化格式决定。

## 3. 条件、状态和关系

`state.work` 描述工作进度，例如 active、complete、blocked。`state.knowledge` 描述证据状态，例如 assumed、reported、observed、derived、checked、refuted、open。维度独立，词汇可扩展。实验完成可以同时报告失败结果，derived 可以与额外条件并存。核心保留内容作者提供的状态声明。

条件项为：

```json
{"text":"P 在指定参数范围内成立","ref":{"id":"P","rev":"2"}}
```

`text` 为完整条件表述，`ref` 可选。引用固定前提修订。选取上下文时保留前提及继承条件。探索记录可以省略条件；正式推导的完整性由所选领域 profile 检查。

关系必需字段为 `id`、`from`、`to`、`kind`。端点均为 `{id,rev}`，其余字段保留。关系方向：

| kind | 方向与含义 |
|---|---|
| depends_on | 使用者 → 前提 |
| assumes | 条件结论 → 假设 |
| supports | 证据 → 被支持记录 |
| cites | 引用者 → 来源 |
| relates_to | 原表达中的有关对象 → 关联对象 |
| uses | 工作或方法 → 使用对象 |
| produces | 工作或方法 → 有来源依据的产物 |
| blocks | 阻碍因素 → 受阻工作 |
| supersedes | 新修订 → 同一对象的旧修订 |

依赖存在不改变证据状态。普通关系图允许环；修订继承必须无环。数学 profile 可另加证明依赖无环规则。

## 4. 修订与冲突

同一 `(namespace,id,rev)` 标识同一不可变记录。内容变化采用新修订。快照以 `heads` 明确选择当前修订；时间戳记录时间，不裁决冲突。

三方合并检查使用共同基线 B、左快照 L、右快照 R。L/R 选择同一修订时相容；一方与 B 相同时，另一方变化可成为候选；两方都离开 B 且选择不同修订时报告冲突。同一记录身份对应不同内容或同一关系 ID 对应不同关系，也构成冲突。参考实现给出检查结果，宿主负责合并和写入。

来源保存原始格式、路径、可选行号及原档案身份。导入器保留原字节，同时生成可查询投影。未知原字段继续保存在投影 body 或原档案中。

## 5. 档案与资源

入口是 `aocx.json`，`records.jsonl` 每行一条记录，`relations.jsonl` 每行一条关系。资源清单记录相对路径、精确字节数、SHA-256 和角色。摘要针对已存储字节；重新序列化后重新计算。

| 入口字段 | 内容 |
|---|---|
| format / version | AOCX / 1.0 |
| namespace | 对象标识的作用域 |
| records / relations | 两个 JSONL 相对路径 |
| heads | ID 到当前修订的映射 |
| profiles | 使用的 profile 标识 |
| required_profiles | 声明的语义操作必须理解的 profile |
| assets | 已包含文件、摘要、字节数和角色 |
| origins | 原始格式、原始资源文件与根路径 |
| external_resources | 可选外部位置、版本和可用性 |
| extensions | 可选扩展元数据 |

角色区分正文、附件、索引、原始档案与视图。完整源码和源码索引分别登记。外部资源明确写 availability:external 或缺失状态，链接不会改变其字节包含范围。

目录可 ZIP 封装。读取端拒绝绝对路径、父目录跳转、符号链接和冲突条目，并设置文件数与展开体积上限。外部取回与程序执行由宿主另行决定。

## 6. 上下文与保全契约

编译目标是上下文值，由已通过档案检查的输入构造。它包含以下七个字段：

| 字段 | 值与来源 |
| --- | --- |
| `namespace` | manifest 的对象命名空间 |
| `records` / `relations` | 已读取 JSONL 中的记录与关系数组，保留顺序与全部 JSON 值 |
| `heads` | manifest 明确指定的当前修订 |
| `profiles` / `required_profiles` | manifest 的 profile 声明 |
| `metadata` | manifest 中除容器字段外的其余字段，包含 `extensions`、`external_resources` 及未知元数据 |

容器字段集合为 `format`、`version`、`namespace`、`records`、`relations`、`heads`、`profiles`、`required_profiles`、`assets`、`origins`。其中记录与关系文件路径、资产清单、原件位置属于档案存储；上下文表示携带解析后的记录图。原文件字节由档案与 `restore` 契约保存。

保全契约格式如下：

```json
{"format":"AOCX-CONTRACT","version":"1.0","fidelity":"exact","selection":{"mode":"all"},"omit_fields":[]}
```

`fidelity` 取 `exact` 或 `projection`。`selection` 为 `{ "mode": "all" }`，或 `{ "mode": "heads", "ids": [ID, ...] }`。指定 ID 时数组非空、唯一且排序；`omit_fields` 为唯一、排序的字段名数组，允许值为 `body`、`extensions`。

| 契约 | 目标构造 | CLI |
| --- | --- | --- |
| `exact` | 整个上下文值，`selection.mode=all`，`omit_fields=[]` | 默认 `compile`；该模式接受全量选择与完整字段 |
| `projection` | 按选择闭包保留记录及端点均保留的关系，再省略已声明字段 | `--mode projection`；可重复 `--select ID`；默认省略 `body`、`extensions`，`--full-fields` 保留全部所选字段 |

局部选择从源 `heads` 中找到每个 ID 的当前修订，递归纳入条件引用、`depends_on`、`assumes` 与 `cites` 的固定目标。历史前提保留原 `rev`。投影 `heads` 是源 head 映射在已保留当前修订上的限制，因此被选入的历史前提可以存在于 `records` 中而没有对应 head。

保全比较必须同时保持 JSON 类型与值。记录身份、逻辑 AST、条件、范围、状态、来源、锚点及未知字段由相同规则处理；`projection` 的省略仅适用于契约明确允许的字段。目标确定后，所有候选必须恢复同一个值。

## 7. 表示封装与可逆编码

### 封装与来源绑定

`AOCX-REP` 1.0 封装具有六个必需字段：

| 字段 | 内容 |
| --- | --- |
| `format` / `version` | `AOCX-REP` / `1.0` |
| `contract` | 本次 `AOCX-CONTRACT` |
| `source` | `namespace`、完整快照的 `snapshot_sha256`、原记录文件的 `records_sha256`、原关系文件的 `relations_sha256` |
| `context` | 按契约得到的目标上下文值 |
| `recovery` | `{ "kind": "self-contained", "scope": "context-values", "target_sha256": SHA256 }` |

快照与目标摘要来自实现的确定性 JSON 比较形式：对象键排序、紧凑分隔符、直接保留 Unicode、有限 JSON 数值，UTF-8 编码且末尾无换行，对应 `SHA256(_content(value).encode("utf-8"))`。原文件摘要来自磁盘中的精确字节。`decode` 检查封装、契约、目标摘要与记录图并返回上下文值。`verify` 进一步读取指定源档案，核对全部源绑定，按契约重建目标并逐值比较；可通过 `--contract` 同时固定接收方预期契约。`exact` 的目标摘要必须与完整源快照摘要一致。

### Wire

内置表示的首行是 ASCII 编码标识，后接 UTF-8 正文：

```text
AOCX/1 <codec-id>
<encoded envelope>
```

编码器必须提供真实 `encode` 与 `decode`，wire 标识必须与其注册 ID 一致。接收方从首行选择 decoder。内置 codec 共用 `CodecRegistry`，默认候选为 `aocx-expr/1`、`aocx-expr-dict/1`，`json/1` 通过 `--codec json/1` 显式加入候选。

`aocx-expr/1` 的通用值使用严格 JSON 标量、数组和对象；常见结构可以写为下表的构造符。`extra` 为附加字段对象，与位置参数定义的字段互斥。

| 构造符 | 位置字段 | 固定或附加内容 |
| --- | --- | --- |
| `Rep` | `contract, source, context, extra` | 固定 `format=AOCX-REP`、`version=1.0`；`recovery` 位于 `extra` |
| `Context` | `namespace, records, relations, heads, profiles, required_profiles, extra` | `metadata` 位于 `extra` |
| `Record` | `id, rev, kind, text, extra` | 其余记录字段位于 `extra` |
| `Relation` | `id, from, kind, to, extra` | 其余关系字段位于 `extra` |
| `Ref` | `id, rev` | 固定修订引用 |
| `Logic` | `expression_string, extra` | 固定 `format=aocx-logic/1`；解析字符串得到开放 AST，恢复为 `expression`；`extra` 与 `format`、`expression` 互斥 |

构造符写为 `Name(arg1,arg2,...)`。解析器按规定的参数数量恢复对象，字段名和值中的任意 Unicode 文本通过 JSON 字符串保存。`Logic` 的第一个参数是第 8 节语法的 JSON 字符串，decoder 将它解析回 AST。`Logic` 是可选的紧凑表示；自由内容中形似逻辑声明的普通 JSON 继续按其数据值保存。实际记录 `logic` 字段的显式协议检查由记录模型负责。函数样式的语法由数据解析器处理。

`aocx-expr-dict/1` 将正文包裹为 `Dict([string,...],expression)`。词典为唯一字符串数组，`@0`、`@1` 等引用对应字符串；引用可以用于字符串值和对象成员名。词典定义、引用和全部标点都计入 wire 成本。`json/1` 的正文为同一完整封装的严格 JSON。

### 候选验收与成本

每个候选依次执行编码、按 wire 解码、完整封装逐值比较、契约和源绑定检查、成本测量。逻辑保全优先于缩写和语言选择，表现为候选准入条件。未通过候选保留结构化淘汰原因；通过候选按 `(cost, wire_bytes, codec_id)` 取最小值。

`--metric bytes` 计算完整 UTF-8 字节数；`characters` 计算解码字符串中的 Unicode 码点数；`tokens` 使用指定 tokenizer 返回的实际 token 序列长度。CLI 的 token 模式要求 `--tokenizer ENCODING` 及可用的 `tiktoken`；Python API 可以提供 tokenizer 回调和标识。报告的 `finite_search=true` 表示最优范围为本次候选集合。

## 8. 显式逻辑结构

记录可以附加 `logic`：

```json
{"format":"aocx-logic/1","expression":{"op":"call","name":"Valid","args":[{"op":"var","name":"x"}]}}
```

`expression` 是含非空 `op` 的 JSON 对象。已知节点按下表检查必需字段；附加字段完整保留。谓词名称、函数名称、自由变量和领域词汇由内容作者定义。内置 `logic/1` profile 支持这一声明；`record.logic` 标明 `format=aocx-logic/1` 时执行结构检查，其余自由结构继续按开放字段保存。

| `op` | 必需字段 | 表达式形式 |
| --- | --- | --- |
| `var` | `name` | `x` |
| `const` | `value`，JSON 标量 | `"text"`、`42`、`true`、`null` |
| `literal` | `text` | `Literal("任意原文")` |
| `call` | `name, args` | `Predicate(x,y)` |
| `set` | `binder, body` | `{x\|Predicate(x)}` |
| `bind` | `name, bindings` | `S[x="value"]`；每个 binding 含 `name, value`，名字唯一 |
| `not` | `body` | `¬(P)` |
| `forall` / `exists` | `binder, body` | `∀x.(P)` / `∃x.(P)` |
| `sequent, and, or, implies, iff, in, eq` | `left, right` | `⊢, ∧, ∨, →, ↔, ∈, =` |

运算符优先级从高到低为 `∈` / `=`、`∧`、`∨`、`→`、`↔`、`⊢`；`→` 右结合，其余二元运算符左结合。括号显式指定分组，量词的作用域由其正文表达式确定。规范渲染对二元表达式和完整量词节点加括号，保持量词与外层运算符的作用域。

Unicode 标识符可直接使用。未知节点、需要额外属性的节点或无法直接拼写的标识通过 `AST(JSON)` 保留；`validate_logic` 在 `opaque_nodes` 中报告未知节点。解析与渲染的验收条件为 AST 的类型和值往返一致。表达式中的断言与推导关系作为作者声明保存，其领域有效性由相应 profile 与证据判断。

## 9. 扩展与协商

`compile --reader capabilities.json` 接收 `codecs`、`profiles` 和可选 `required_profiles`。声明 `codecs` 时，只允许其中列出的已实现 decoder；声明 `profiles` 时，源与读者的必需 profile 必须位于双方支持的交集中。每个候选仍通过相同保全验收。

通用 `negotiate` 接口继续支持 `versions`、`profiles`、`codecs`、`required_profiles`、`accepts_lossy` 与 `codec_modes`。外部 codec 的能力协商结果标记实现需求；实际编译通过 `CodecRegistry` 提供 `Codec(id, encode, decode)`。这两个接口分别处理共同能力和实际可执行编码。

未知可选字段与 profile 原样保留。未知必需 profile 使相关语义操作返回 `unsupported`，保存模式保留原数据。核心检查、领域检查和语言评估分别报告。语言视图绑定具体任务、读者与证据，见[兼容与语言 profile](profiles.md)。

新 profile 声明标识与版本、适用对象、字段含义、关系方向、保护信息、检查方法、依赖、输出范围、回退表示和测试向量。JSON Schema 随本地资源提供，检查器由宿主明确注册。同一主版本保持已有字段含义；改变字段语义或关系方向时采用新主版本或新限定名称。

## 10. 兼容接口与实现边界

`capsule` / `parse_capsule` 保留 `table-jsonl/1` 接口。头部继续包含命名空间、原记录与关系摘要、列定义、所选固定修订、计数和省略范围。记录行依次为 `record, id, rev, kind, text, extra`；关系行依次为 `relation, id, from, kind, to, extra`。`--full` 保留所选记录与关系的全部字段，默认 `handoff` 声明省略项。该兼容表示的恢复范围由其头部和行协议定义；完整上下文快照使用 `compile --mode exact`。

`scripts/aocx.py` 保持 CLI 与历史 Python API 入口，内部职责见[架构模块表](architecture.md#2-编译管线与模块边界)。编译核心、图、存储、适配和视图使用 Python 标准库；token 计量按需接入具体 tokenizer。

内置 wire 解析限制为 64 MiB、128 层嵌套、100 万个值节点。解码器另设 `MAX_EXPANDED_STRING_BYTES=64 MiB`，累计计算展开后字符串的 UTF-8 字节：显式字符串键和值、词典定义及每次引用、构造符生成的字段和固定标记，以及 `Logic` 解析所得 AST 的全部字符串键和值。逻辑表达式原文同时保留在计数中，因此该额度采用保守统计。字典引用的字符串字节数预先缓存，重复引用按次数累计。

显式逻辑表达文本限制为 16 MiB，AST 检查限制为 128 层嵌套和 10 万个 JSON 值节点。超过限制返回结构化错误。参考实现按 Python JSON 规则读取数值：整数使用 Python 整数，小数使用有限浮点数；十进制逐位精度使用字符串、表达式对象或原始字节保存。

执行证据位于 `assets/validation/`。每份结果绑定其输入、环境、命令与检查范围；论文实验保留原作者和原测试范围。
