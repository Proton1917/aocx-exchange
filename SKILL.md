---
name: aocx-exchange
description: "Compile, import, preserve, optimize, or validate context for another agent using AOCX. Use for explicit context handoffs, project or research archives, reversible expression encodings, open logic ASTs, AOCI/GBCX compatibility, and task-conditioned language views. Compare complete representation costs under an executable preservation contract."
---

# AOCX Exchange

以保全契约编译交接上下文：先确定必须保留的对象和值，再对实际可解码的候选测量完整成本。日常仓库索引读取与维护使用项目原生 AOCI MCP；交接指定内容时使用 AOCX 档案与编译命令。来源范围与原生交付约定见 [AOCI 绑定说明](references/mcp-binding.md)。

## 工作流程

1. 确定来源、接收方、任务范围和保全要求。默认使用 `exact`，保留整个上下文值。局部交接使用显式 `projection` 契约，并记录选择与省略项。保留输入，转换结果写入新路径。
2. 为记录提供 `id`、`rev`、`kind`、`text`。将探索内容保留在自由文本或 `body`，按需要附加条件、范围、状态、来源、量与关系。保留新领域种类和未知字段。明确提供的逻辑结构可保存为 `logic={format:"aocx-logic/1",expression:AST}`；以 `logic` 命令检查和渲染。
3. 将 `AOCX_SKILL_DIR` 设为当前 `SKILL.md` 所在目录的绝对路径，从该目录调用 `scripts/aocx.py`。输入和输出相对任务工作目录解析。档案与表示操作会计算或核验 SHA-256，依宿主对输入的授权执行。

```bash
python3 "$AOCX_SKILL_DIR/scripts/aocx.py" create --records records.jsonl --relations relations.jsonl --out exchange --namespace project-name
python3 "$AOCX_SKILL_DIR/scripts/aocx.py" import-aoci path/to/cognition aoci-exchange --namespace project-name
python3 "$AOCX_SKILL_DIR/scripts/aocx.py" import-gbcx archive.zip gbcx-exchange --namespace research-project
python3 "$AOCX_SKILL_DIR/scripts/aocx.py" validate exchange
python3 "$AOCX_SKILL_DIR/scripts/aocx.py" compile exchange --out context.aocx --report compile-report.json
python3 "$AOCX_SKILL_DIR/scripts/aocx.py" verify exchange context.aocx
python3 "$AOCX_SKILL_DIR/scripts/aocx.py" decode context.aocx --out context.json
```

4. 阅读创建、导入和验证报告，核对引用、修订、数据类型、路径与资源摘要。将不确定性和开放问题保留为数据。`exact` 覆盖记录图、heads、profile 和 manifest 元数据；附件与原件字节随档案保留，原件恢复使用 `restore`。
5. 通过 `compile`（别名 `optimize`）比较候选。默认使用可逆表达式及共享词典编码；可重复 `--codec` 指定候选，`--codec json/1` 加入 JSON 基线。用 `--reader capabilities.json` 限定接收方能力。字节、字符与 token 分开计量；token 模式需要真实 tokenizer，CLI 使用 `--metric tokens --tokenizer ENCODING` 及可用的 `tiktoken`。
6. 使用 `--mode projection --select ID` 选择局部上下文，沿固定修订的条件与依赖计算闭包。默认省略 `body`、`extensions`；`--full-fields` 保留所选对象全部字段。用 `verify` 核对源档案；需要固定接收策略时加 `--contract expected-contract.json`。保留历史前提的原修订和源 head 语义。
7. 对任务条件语言视图保留原档案并执行 `check-view`。通过 [profile 约定](references/profiles.md#babeltele-语言视图)绑定正文、任务、读者、源快照及报告。分别报告结构、证据绑定和宿主实际评估；以实际评估支持作为唯一任务上下文的选择。
8. 交付表示、编译报告和所需原档案，说明保全范围、实测成本、验证结果及具体未解析引用。最优性声明限定到本次候选集合和成本度量。依当前环境的文件流程保存普通交付物。

已有调用可继续使用 `capsule --full` 与 `parse_capsule`，其 `table-jsonl/1` wire 保持兼容；完整上下文恢复的主入口为 `compile` / `decode` / `verify`。

## 规范与检查

- [核心规范](references/specification.md)：记录、图、修订、保全契约、表示封装、wire 与逻辑 AST。
- [架构说明](references/architecture.md)：模块职责、候选准入、有限优化与扩展 API。
- [Profile](references/profiles.md)：AOCI/GBCX 映射、原件恢复、语言视图与证据绑定。
- [MCP 绑定](references/mcp-binding.md)：原生 AOCI 读取、收据、治理与交接范围。
- [验证方法](references/validation.md)：可复现命令、验收条件、成本和读者评估。
- [研究来源](references/research.md)：原论文、仓库与采用范围。

Schema 与样例位于 `assets/`。实现检查按受影响行为选择测试，将临时文件放在任务授权范围内。全量入口：

```bash
python3 -m unittest discover -s "$AOCX_SKILL_DIR/scripts/tests" -v
```

工作进度和证据状态分别记录。数据契约由相应验证器检查，领域结论通过其证据评价。原生 AOCI 的收据、基线、批准和恢复继续使用原系统流程。
