# AOCX 检查与评估

本文给出档案、保全契约、编译表示、显式逻辑和语言视图的检查方法。数据契约见[核心规范](specification.md)，模块职责见[架构说明](architecture.md)，原格式映射和评估绑定见 [profile 说明](profiles.md)。

## 目录

1. 检查层次
2. 程序
3. 验收矩阵
4. 成本测量
5. 语言视图与读者评估
6. 执行证据

## 检查层次

档案检查处理 UTF-8/JSON、必需字段类型、ID 与修订冲突、关系端点、条件引用、当前修订、资源摘要和路径。新种类、未知可选字段、自由文本按开放内容保留。

编译检查在已校验的档案上执行保全契约：构造目标、编码候选、实际解码、比较完整封装和目标值。`exact` 验收整个上下文快照；`projection` 验收声明的选择闭包和字段省略。`logic_preserved` 对应声明范围内逻辑字段及结构的逐值保全。

领域检查由对应 profile 定义。数学可以核对量词、假设和证据；软件可以核对接口与测试版本。任务条件语言评估检验指定读者是否能用视图完成任务，报告样本、模型、评分标准和结果。各层分别记录检查范围。

## 程序

从仓库根目录运行以下命令，使用新的输出目录 `validation-run`。以技能方式调用时，将 `AOCX_SKILL_DIR` 设为包含 `SKILL.md` 的绝对目录，再用该目录下的 `scripts/aocx.py`；输入、输出仍相对任务工作目录解析。

```sh
python3 scripts/aocx.py validate assets/examples/software
python3 scripts/aocx.py compile assets/examples/software --out validation-run/context.aocx --report validation-run/compile.json
python3 scripts/aocx.py verify assets/examples/software validation-run/context.aocx
python3 scripts/aocx.py decode validation-run/context.aocx --out validation-run/context.json
python3 scripts/aocx.py compile assets/examples/math --mode projection --select math/conclusion --full-fields --out validation-run/selected.aocx --report validation-run/selected.json
python3 scripts/aocx.py verify assets/examples/math validation-run/selected.aocx
```

`compile.json` 保存候选集合、准入结果、成本、选中的 codec、保全契约和源绑定。`context.aocx` 是独立解码输入，`context.json` 是恢复的上下文值。`verify` 从原档案重建目标并检查来源与值一致；`decode` 的报告注明其执行的是表示内部检查。

需要固定接收策略时，将预期契约保存为独立 JSON 文件并传给 `verify --contract expected-contract.json`。精确策略的内容为：

```json
{"format":"AOCX-CONTRACT","version":"1.0","fidelity":"exact","selection":{"mode":"all"},"omit_fields":[]}
```

验证器将该策略与表示声明逐值比较，因此来源、目标与接收策略可以同时核验。编译、解码、逻辑声明和报告写入采用新路径；路径已存在时返回错误，输入保持可复核。

显式逻辑的解析与往返检查入口：

```sh
python3 scripts/aocx.py logic --expression 'S[x="GenshinImpact"]⊢x∈{y|SelfDev(Dev(x),y)∧OpenAdvGame(y)}' --out validation-run/logic.json
python3 scripts/aocx.py logic --input validation-run/logic.json
```

`logic` 输出声明、规范渲染文本与结构结果，`--input` 接受 AST 或完整 `aocx-logic/1` 声明。兼容接口按各自协议验证：

```sh
python3 scripts/aocx.py capsule assets/examples/software --full --out validation-run/legacy-table.aocx
python3 scripts/aocx.py check-view assets/examples/math assets/examples/math_view.babeltele.json
python3 scripts/aocx.py merge-check base left right
```

档案相关操作会计算或核验 SHA-256，操作范围遵循宿主对所用输入的授权。错误报告定位到对象、修订、字段或资源路径。未知必需 profile 返回对应不支持范围，`validate --preserve-only` 提供保存检查路径。

## 验收矩阵

| 对象 | 方法与通过条件 | 主要验证入口 |
| --- | --- | --- |
| 精确上下文 | decode 后的命名空间、所有记录与关系、heads、profile、元数据与源快照类型和值一致 | `test_optimizer.py`、`verify` |
| 投影 | 选中当前修订，完整纳入固定前提闭包，省略项与契约一致 | `test_optimizer.py` |
| 历史前提 | 原 `rev` 保持，源中未被保留的当前修订保持在投影 head 映射之外 | `test_optimizer.py` |
| 候选准入 | 失真、不可解码、身份错配、读者不支持的候选被淘汰，原因出现在报告中 | `test_optimizer.py`、`test_codecs.py` |
| 有限优化 | 最终 `(cost, wire_bytes, codec_id)` 等于全部通过候选的最小值 | `test_optimizer.py` |
| 完整成本 | 头部、契约、来源、词典、恢复信息及正文统一计量 | `compile --metric` |
| 显式逻辑 | 解析与渲染保留 AST；分组、量词、绑定、Unicode 和未知节点可往返 | `test_logic.py` |
| 解析边界 | 重复键、非有限值、越界词典引用、超限嵌套或展开字符串额度等返回结构化错误 | `test_codecs.py`、`test_logic.py` |
| 来源漂移 | 记录、关系、head、profile 或元数据变化使旧来源绑定核验失败 | `verify`、`test_optimizer.py` |
| 原件恢复 | 原 ZIP 及每个原文件的字节和摘要相同，包含原换行和 BOM | `test_core.py`、旧格式验证脚本 |
| 原字段与未知扩展 | 投影保存所声明原 JSON，精确编译保持全部未知值 | `test_core.py`、`test_aoci_protected.py` |
| 语言视图 | 保护字段、闭包、源绑定和评估摘要均对应当前输入 | `check-view`、视图契约测试 |
| 版本冲突 | 同一身份异值、关系 ID 冲突和三方分叉均可定位 | `test_core.py`、`merge-check` |

表内文件均位于 [`scripts/tests/`](../scripts/tests/)。按受影响行为选择测试；全量入口为：

```sh
python3 -m unittest discover -s scripts/tests -v
```

执行结果应记录当前提交或文件版本、Python 版本、命令、用例数与失败信息。表内条件是验收约定，实际通过范围以当次执行结果为准。

## 成本测量

在相同源档案、契约、读者能力与候选集合上比较完整表示。字节、字符和 token 使用独立单位，报告明确 `metric`。字符数按 Unicode 码点计算。token 数由指定 tokenizer 直接测量，CLI 需要可用的 `tiktoken` 及所选编码。

```sh
python3 scripts/aocx.py compile assets/examples/software --codec aocx-expr/1 --codec aocx-expr-dict/1 --codec json/1 --metric bytes --out validation-run/bytes.aocx --report validation-run/bytes.json
python3 scripts/aocx.py compile assets/examples/software --metric characters --out validation-run/characters.aocx --report validation-run/characters.json
python3 scripts/aocx.py compile assets/examples/software --metric tokens --tokenizer cl100k_base --out validation-run/tokens.aocx --report validation-run/tokens.json
```

Python API 的 tokenizer 回调必须返回实际 token 序列，并提供 tokenizer 标识。候选报告中的成本覆盖最终 wire 全文；有限候选最优与节省幅度分别记录。比较节省幅度时写明基线 codec、相同目标和计算公式。

### 已记录的字节测量

[`representation_compiler.json`](../assets/validation/representation_compiler.json) 记录 2026-11-23、Python 3.12.14 下的精确模式测量。每个样本都以相同 `AOCX-REP` 封装的 `json/1` 为基线，在三个内置 codec 中完成往返与源档案核验，比较完整 UTF-8 wire。节省比例按 `1 − selected_bytes / baseline_bytes` 计算。

| 输入 | 样本类型 | JSON 基线（字节） | 选中表示（字节） | 节省比例 |
| --- | --- | ---: | ---: | ---: |
| math | 仓库数学示例 | 1915 | 1491 | 22.141% |
| document | 仓库文档示例 | 2133 | 1656 | 22.363% |
| software | 仓库软件示例 | 2567 | 1980 | 22.867% |
| formal | 仓库显式逻辑示例 | 5417 | 3790 | 30.035% |
| repeated-context-128 | 128 条共享重复内容的合成记录 | 55488 | 15538 | 71.998% |

这五个样本都选中 `aocx-expr-dict/1`。合成样本专门观察重复字符串复用，结论按该构造范围解释。该次报告的 token 测量状态为 `not-run`。通过以下命令复现当前工作树上的字节测量：

```sh
python3 assets/validation/measure_compiler.py --out validation-run/measurements.json
```

端到端性能另外计入编码、输入处理、解码、取回和重试：

\[
C_{\mathrm{total}}=C_{\mathrm{encode}}+C_{\mathrm{input}}+C_{\mathrm{decode}}+C_{\mathrm{retrieve}}+C_{\mathrm{retry}}.
\]

各项使用统一的时间、token 或费用口径。wire 长度报告支持表示选择；端到端加速由实际运行测量支持。

## 语言视图与读者评估

视图评估先固定源快照、压缩正文、任务、读者模型、tokenizer 和生产参数。报告采用 `AOCX-EVALUATION` 1.0，将 `view_sha256` 绑定去掉顶层 `evaluation` 后的完整视图，将 `source_snapshot_sha256` 绑定完整源上下文。报告作为有摘要的档案资产引用。

任务集可覆盖事实检索、身份、关系方向、共同前提、有效修订、量词、单位、例外、条件结论和未知答案。记录问题、基线答案、模型版本、提示词摘要、参数、评分方法、阈值和实际输出。关键字段可采用全对标准，每个结果保留样本与领域范围。

`check_view(..., evaluator=...)` 在结构与证据绑定通过后将报告、视图、源快照的独立副本交给宿主评估器。评估器返回严格 `True` 时，结果中的 `semantic_evaluation_verified` 和 `eligible` 才成立。CLI 的 `check-view` 提供结构与绑定结果，实际模型评估由宿主执行。旧 `passed` 声明保留为历史声明，报告其绑定状态。

## 执行证据

[`assets/validation/`](../assets/validation/) 保存各次验证与兼容样本结果；每份记录按其中声明的样本、环境和执行范围引用。本次编译器验证的环境、命令和实际结果见 [`compiler_verification.json`](../assets/validation/compiler_verification.json)，逐项执行日志见 [`compiler_tests.txt`](../assets/validation/compiler_tests.txt)，完整 wire 测量见 [`representation_compiler.json`](../assets/validation/representation_compiler.json)。

`core_verification.json`、`aoci_projection.json`、`gbcx_roundtrip.json` 等既有记录属于各自初始实现或固定样本的历史证据。当前编译与结构测试按上述命令运行，结果与其实际日志对应。

[`assets/examples/`](../assets/examples/) 中的领域样例用于可复现的数据与接口检查。论文实验与本地执行分别保留来源；跨模型效果和端到端性能由实际运行的评估证据支持。
