# AOCI MCP 与 AOCX 宿主适配

## 职责

AOCI MCP 负责项目索引的日常查阅与维护。Codex 在目标项目的会话中调用已配置的 AOCI MCP。需要交接时，Codex 调用本地 AOCX 命令，将选定来源转换为档案或阅读视图。索引批准、CAS、基线与恢复由原生 AOCI 流程处理。

AOCX 提供离线适配器和可导入的 Python 模块。MCP 工具的调用方式以服务端 schema 和运行规则为准。

## 原生工具与读取

通过 `aoci_rules` 获取会话规则。完整索引使用 `aoci_overview`，定点查询使用 `aoci_get_entries` 或 `aoci_search`。索引维护使用 `aoci_maintain` 和当前工具返回的写入流程。标签字典等元信息可通过 `aoci_header` 查阅。

完整 Whole-Index 请求沿 `next_cursor` 读取至 `completed=true`，保持范围、范围标识和原始顺序，并按原生合同确认交付和提交认知验证。`check_only=true` 返回检查点事实。

## 索引交接

以含 `aoci.txt` 的项目目录或 AOCI 快照 ZIP 作为输入。目录导入读取 `aoci.txt` 及其声明的卷。ZIP 导入将输入档案原样保存在结果中，制作快照时按接收方的授权范围选择文件。操作会计算和核验 SHA-256，摘要范围以宿主授权为准。[检查方法](validation.md#程序)

将 `AOCX_SKILL_DIR` 设为技能入口 `SKILL.md` 所在目录的绝对路径。在目标项目根目录运行以下命令，输出写入新目录。

```sh
python3 "$AOCX_SKILL_DIR/scripts/aocx.py" \
  import-aoci . aoci-exchange --namespace project-name
```

导入保留原索引字节和条目身份，将职责、关系、接口与约束映射为 AOCX 记录。局部 MCP 查询结果可将原始响应存入 `source` 或 `evidence` 记录的 `body`，并标明来源项目和查询范围。使用完整档案或 `capsule --select` 生成的阅读视图时，根据导入报告识别映射范围和缺失的关联目标，并按接收方权限核对交付内容。

原生正文、交付收据和认知验证按 AOCI 的合同处理。AOCX 报告记录转换和档案检查的结果。接收方可以按来源身份回取详情。

## MCP 载荷

MCP 工具可以提供 structuredContent 和文本块，工具自己的 outputSchema 规定返回结构。宿主可以在自己的结果、资源或独立适配工具内承载 AOCX，原有 AOCI 工具仍遵循原生 schema。

如需提供宿主适配工具，可使用一个入口加 operation 参数，按需资源承载大档案。常驻说明保持简短。对象形式 structuredContent 并附序列化文本可以覆盖所核对的 MCP 版本。初始交付的工具直接本地运行。

## 来源

- https://github.com/aoci-spec/aoci-code/blob/3d8e4b0048b7ae93d671ffae39db73a44db434d3/spec/public/aoci-mcp-runtime-v1.txt
- https://github.com/aoci-spec/aoci-code/blob/3d8e4b0048b7ae93d671ffae39db73a44db434d3/spec/public/aoci-overview-delivery-v1.txt
- https://modelcontextprotocol.io/specification/2025-11-25/server/tools
- https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/server/tools.mdx
