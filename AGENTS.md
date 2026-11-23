# AOCX Exchange 项目协作规范

## 格式与实现

- 以 [AOCX/1 核心规范](references/specification.md)和 [CLI 入口](scripts/aocx.py)核对数据契约。修改公开字段、关系方向、修订语义或编码时，同步维护受影响的规范、JSON Schema、示例和检查。
- 通用交换逻辑放在 `scripts/aocx.py`，旧格式解析及字段映射放在 `scripts/adapters/`。参考实现使用 Python 标准库。领域特定规则通过对应 profile 描述，通用记录保留自由文本、未知类型与未知字段。
- 导入 AOCI 或 GBCX 时保留原始字节和来源，投影声明映射范围。选择交接记录时保留固定修订的前提及保护字段。分别报告结构检查与读者任务评估。[兼容规则](references/profiles.md) · [验证方法](references/validation.md)
- 使用 `python3 -m unittest discover -s scripts/tests -v` 运行现有契约测试。依变更范围选择检查，涉及档案操作时遵循任务授权的摘要范围。转换和恢复写入任务目录内的新路径。

<!-- aoci:begin -->
## 仓库 AOCI 索引

`aoci.txt` 声明本仓库索引及其卷。`aoci.meta.txt` 定义标签字典和条目规则，`aoci.code.txt` 记录各受管理文件的职责、关联、接口和约束。随仓库提交正式索引、配置与基线。`.aoci/.gitignore` 管理运行记录与正式资产的 Git 边界。

- 新会话通过 `aoci_rules` 取得已连接服务的运行合同，依该合同使用 `aoci_overview` 加载完整索引。以任务涉及的源码、配置和测试为直接证据。
- 初始化和恢复遵循当前版本的 `aoci index agent guide --agent codex --json`。受管理文件达到稳定状态后，通过 `aoci_maintain` 获取待更新候选，由模型依据源码编写条目，再用 `aoci_update_entry` 提交完整批次。以工具给出的对齐结果完成维护。
- AOCX 导入和交接视图遵循[宿主适配说明](references/mcp-binding.md)。本仓库 AOCI 索引的维护通过原生 AOCI 流程完成。
<!-- aoci:end -->
