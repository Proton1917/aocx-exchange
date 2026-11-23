# AOCX 检查与语言评估

## 检查层次

结构检查处理确定性交换问题：UTF-8/JSON、必需字段类型、ID/修订冲突、关系端点、条件引用、当前修订、文件摘要和路径。新领域、未知可选字段、自由文本原样接收。

领域检查由选定 profile 定义。数学可以检查正式命题的量词、假设和证据；软件可以核对接口与测试版本。具体检查绑定到适用对象，探索记录保持其身份和状态。

语言评估检验压缩视图是否足够支持指定读者和任务。它与档案完整性分别报告。

## 程序

将 `AOCX_SKILL_DIR` 设为技能入口 `SKILL.md` 所在目录的绝对路径。输入和输出路径以任务工作目录为基准。`create`、`import-aoci` 和 `import-gbcx` 计算资源摘要并检查生成的档案。`validate`、`restore`、`capsule`、`check-view` 和 `merge-check` 核验所读档案的资源摘要。`capsule` 和 `restore` 还返回各自输出文件的 SHA-256。操作范围以宿主对数据和摘要用途的授权为准。

```sh
python3 "$AOCX_SKILL_DIR/scripts/aocx.py" validate exchange
python3 "$AOCX_SKILL_DIR/scripts/aocx.py" capsule exchange --full --out full.aocx
python3 "$AOCX_SKILL_DIR/scripts/aocx.py" check-view exchange language-view.json
python3 "$AOCX_SKILL_DIR/scripts/aocx.py" merge-check base left right
```

测试套件也会计算摘要并创建临时文件。按受影响的行为选择测试，并将临时目录设在任务允许写入的范围内。全量测试入口为 `python3 -m unittest discover -s "$AOCX_SKILL_DIR/scripts/tests" -v`。

错误定位到对象/修订、字段或资源路径。修复时保留原来源。未知必需 profile 返回不支持的语义范围；保存模式保留数据。程序通过表明所执行的数据契约检查通过。

## 兼容验收

| 项目 | 判定 |
|---|---|
| 档案恢复 | 原 ZIP 字节及 SHA-256 相同 |
| 目录恢复 | 各原文件字节相同，包括 BOM/换行 |
| 原字段 | body 与原 JSON 对象逐值一致 |
| 条件 | 直接假设及继承条件完整，固定引用可解析 |
| 关系 | 方向和原含义保持，强关联保持为关联 |
| 状态 | 工作进度、证据状态分别保留 |
| 未知扩展 | 全量往返保持其值 |
| 修订 | 身份冲突和三方分叉可定位 |
| 紧凑编码 | full 解码后 JSON 值一致 |
| 自由表达 | 新种类、混合语言、公式、推测笔记可存取 |

## 模型评估

任务集覆盖事实检索、对象身份、关系方向、共同前提、有效版本、量词/不等号/单位/例外、条件结论和未知答案。数学、软件、文档/数据分别报告。

记录样本版本、问题/基线答案、编码器与读者版本、tokenizer、提示词摘要、参数、评价方法与输出。接收 Agent 独立回答，输入保持题目实际需要的信息。相关模型、任务或源内容变化时重测对应范围。

确定性编码按 JSON 值往返验收；语义编码同时报告保护字段一致性和任务得分。关键字段可以采用全对标准，样本上的通过保留其范围。

## 成本

完整计入头部、词典、保护字段、编码指令与正文。字节数、字符数和指定 tokenizer 的 token 数分别报告。端到端成本包含编码、输入处理、读者推理、取回及重试。

\[
C_{\mathrm{total}}=C_{\mathrm{encode}}+C_{\mathrm{input}}+C_{\mathrm{decode}}+C_{\mathrm{retrieve}}+C_{\mathrm{retry}}.
\]

各项按统一时间、token 或费用口径实测。先满足信息要求，再比较成本。空的查询相关视图显式记录选择范围与原因，使其与缺失交付可区分。

## 执行记录

实际程序结果保存在 assets/validation。论文原实验和本地执行分别标注。BabelTele 示例用于接口与保护字段检查；跨模型语义和端到端加速由明确运行的评估报告支持。
