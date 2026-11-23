# AOCX Exchange

AOCX（Agent Object and Context Exchange，智能体对象与上下文交换）是受保全契约约束的上下文编译器。它把项目、研究和文档档案编译为可独立解码的表示：先确定必须保留的对象、修订、条件、关系与元数据，再对实际可解码的候选测量完整传输成本，选出满足契约的最小候选。

逻辑保全是候选准入条件。自然语言、混合语言、公式和探索笔记作为原始内容保存；显式逻辑表达可以附加为开放 AST。编码器通过结构因子化和共享词典减少重复，每个结果都经过真实解码与逐值比较。[核心规范](references/specification.md)定义保全范围，[架构说明](references/architecture.md)说明模块与有限优化问题。

## 编译与恢复上下文

在仓库根目录运行。字节与字符成本使用 Python 3.9 或更高版本的标准库；token 成本需要可用的 `tiktoken` 及指定编码。

```sh
python3 scripts/aocx.py validate assets/examples/software
python3 scripts/aocx.py compile assets/examples/software --out context.aocx --report compile-report.json
python3 scripts/aocx.py verify assets/examples/software context.aocx
python3 scripts/aocx.py decode context.aocx --out context.json
```

`compile` 默认使用 `exact` 契约，保留整个上下文值：命名空间、全部记录与关系、当前修订、profile 和档案元数据。`decode` 从表示本身恢复这些值；`verify` 进一步与指定源档案核对。附件与导入原件由原档案保存，使用 `restore` 恢复原始字节。

默认候选为 `aocx-expr/1` 和 `aocx-expr-dict/1`。输出首行为 `AOCX/1 <codec-id>`，正文携带契约、来源绑定、目标上下文与恢复摘要。`json/1` 可作为显式候选加入比较。编译报告在标准输出中列出各候选成本、淘汰原因、选中的 codec 和保全结果；`--report` 同时保存 JSON 报告，`optimize` 是 `compile` 的别名。

```sh
python3 scripts/aocx.py compile assets/examples/software --codec aocx-expr/1 --codec aocx-expr-dict/1 --codec json/1 --metric bytes --out compared.aocx
python3 scripts/aocx.py compile assets/examples/software --metric tokens --tokenizer cl100k_base --out token-context.aocx
```

选择局部交接范围时使用 `projection`。`--select` 从对象当前修订出发，纳入固定修订的条件与依赖闭包；默认省略记录、关系的 `body` 和 `extensions`，`--full-fields` 保留所选对象的全部字段。历史前提保持原修订身份，`heads` 仅保留源档案实际选中的当前修订。

```sh
python3 scripts/aocx.py compile assets/examples/math --mode projection --select math/conclusion --full-fields --out selected.aocx
```

接收方可通过 `--reader capabilities.json` 限定支持的 codec 与 profile。成本包含完整输出中的头部、契约、来源绑定、共享词典和正文。比较结论限定为本次已检查的有限候选集合及指定成本度量。

## 记录、逻辑和原始档案

记录至少包含 `id`、`rev`、`kind`、`text`；关系连接具体修订。`text` 保存自由表达，条件、状态、来源、保护锚点和未知扩展随记录保留。显式逻辑放在可选 `logic` 字段中，其格式为 `{ "format": "aocx-logic/1", "expression": AST }`。谓词名称与领域解释由内容作者提供，解析器检查结构并支持可逆渲染。

```sh
python3 scripts/aocx.py logic --expression 'S[x="GenshinImpact"]⊢x∈{y|SelfDev(Dev(x),y)∧OpenAdvGame(y)}' --out logic.json
python3 scripts/aocx.py create --records records.jsonl --relations relations.jsonl --out exchange --namespace my-project
python3 scripts/aocx.py import-aoci path/to/index index-exchange --namespace project-index
python3 scripts/aocx.py import-gbcx archive.zip research-exchange --namespace research
python3 scripts/aocx.py restore research-exchange restored.zip
```

导入 AOCI 时提供含 `aoci.txt` 及声明卷的目录；导入 GBCX 时可提供 ZIP。适配器保存原件并生成统一记录。`check-view` 核对 BabelTele 视图的源绑定、保护字段和评估证据绑定；读者完成具体任务的效果由对应评估报告记录。已有 `capsule`、`parse_capsule` 和 `table-jsonl/1` 接口继续提供兼容路径。[兼容与语言 profile](references/profiles.md)列出各自范围。

## 仓库结构与验证

| 路径 | 职责 |
| --- | --- |
| [`scripts/aocx.py`](scripts/aocx.py) | CLI 与历史 Python API 兼容入口 |
| [`scripts/aocx_core/contracts.py`](scripts/aocx_core/contracts.py) | 上下文快照、保全契约、选择闭包与逐值比较 |
| [`scripts/aocx_core/optimizer.py`](scripts/aocx_core/optimizer.py) | 编码、解码、验收、测量与候选选择 |
| [`scripts/aocx_core/codecs.py`](scripts/aocx_core/codecs.py) | 共享 codec 注册表及表达式、词典、JSON 编解码器 |
| [`scripts/aocx_core/logic.py`](scripts/aocx_core/logic.py) | 开放逻辑 AST、结构检查、解析与渲染 |
| [`scripts/aocx_core/`](scripts/aocx_core/) | 图模型、档案存储、旧格式导入、视图与能力协商 |
| [`scripts/adapters/`](scripts/adapters/) | AOCI 和 GBCX 的原生格式映射 |
| [`assets/schemas/`](assets/schemas/) 与 [`assets/examples/`](assets/examples/) | JSON Schema 与可复现示例 |
| [`references/`](references/) | 规范、架构、兼容范围、[验证方法](references/validation.md)和研究来源 |
| [`SKILL.md`](SKILL.md) | 智能体编译与交接上下文的操作入口 |

契约测试入口：

```sh
python3 -m unittest discover -s scripts/tests -v
```

AOCI 维护本仓库随源码演进的项目索引，从 [aoci.txt](aoci.txt) 进入。索引维护、交付确认与基线使用原生 AOCI 流程；AOCX 可将指定索引内容导入并编译为交接表示。具体操作见 [AOCI 绑定说明](references/mcp-binding.md)。
