# AOCX Exchange

AOCX（Agent Object and Context Exchange，智能体对象与上下文交换）为项目、研究和文档工作提供上下文交换格式及本地参考实现。记录以 `id`、`rev`、`kind`、`text` 标识对象、修订、类别和正文，关系连接具体修订。条件、来源、状态和领域扩展可以随记录一起交接。

AOCI 为本仓库维护随源码演进的项目索引，记录文件职责、关联、接口和约束。AOCX 为跨任务的交接提供档案和阅读视图，并支持把 AOCI 索引作为输入。仓库自身的索引从 [aoci.txt](aoci.txt) 进入，AOCI MCP 的接入方式见[宿主适配说明](references/mcp-binding.md)。

## 命令行用法

在仓库根目录运行。命令行使用 Python 3.9 或更高版本及其标准库。

```sh
python3 scripts/aocx.py --help
python3 scripts/aocx.py validate assets/examples/software
```

创建档案时准备两份 UTF-8 JSONL 文件，每行一条记录或关系。使用新路径存放档案和交接视图。

```sh
python3 scripts/aocx.py create --records records.jsonl --relations relations.jsonl --out exchange --namespace my-project
python3 scripts/aocx.py capsule exchange --full --out context.aocx
```

`capsule --full` 保留记录和关系的全部 JSON 值。默认交接视图在头部声明选取范围与省略项。`--select` 按对象选取内容，并纳入引用条件和依赖前提。

导入 AOCI 时提供含 `aoci.txt` 及其已声明卷的目录，导入 GBCX 时可以提供 ZIP 档案。导入结果保留原始资料并生成统一的记录与关系。`restore` 恢复导入时保存的原件。

```sh
python3 scripts/aocx.py import-aoci path/to/index index-exchange --namespace project-index
python3 scripts/aocx.py import-gbcx archive.zip research-exchange --namespace research
python3 scripts/aocx.py restore research-exchange restored.zip
```

`check-view` 核对 BabelTele 视图的来源绑定、引用和保护字段。视图能否支持指定读者完成任务，由独立的模型评估确定。[兼容与语言视图](references/profiles.md)说明了导入范围和检查方式。

## 仓库结构与验证

| 路径 | 内容 |
| --- | --- |
| [`scripts/aocx.py`](scripts/aocx.py) | 交换格式、命令行、档案与视图检查 |
| [`scripts/adapters/`](scripts/adapters/) | AOCI 和 GBCX 导入适配器 |
| [`assets/schemas/`](assets/schemas/) 与 [`assets/examples/`](assets/examples/) | JSON Schema 及软件、数学、文档档案示例 |
| [`references/`](references/) | [格式规范](references/specification.md)、[验证方法](references/validation.md)与[研究来源](references/research.md) |
| [`SKILL.md`](SKILL.md) | 智能体使用 AOCX 交接上下文的操作说明 |

现有测试覆盖记录与关系、旧格式导入与恢复、紧凑视图以及修订冲突。涉及档案完整性的操作与测试会计算或核验 SHA-256。

```sh
python3 -m unittest discover -s scripts/tests -v
```
