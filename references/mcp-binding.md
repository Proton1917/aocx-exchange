# AOCI MCP 与 AOCX 宿主适配

## 职责

AOCI 继续提供软件认知 MCP；AOCX 核心负责转换、档案和视图检查；宿主适配层连接两者；薄 Skill 按需指导调用。原生批准、CAS、Baseline 与恢复流程保持其原有语义。

本版提供离线适配器与可导入 Python 核心，以下规则定义在线宿主的接入方式。服务端工具 schema 仍以原系统为准。

## 原生工具与读取

读取：aoci_rules、aoci_overview、aoci_get_entries、aoci_search。

维护：aoci_maintain、aoci_update_entry、aoci_remove_entry。

证据：aoci_header、aoci_report。

完整 Whole-Index 请求沿 next_cursor 读取至 completed=true 且 continuation_required=false，保留相同 scope、scope identity、原始顺序和交付证据。check_only=true 是检查点，其范围随元数据保留。

使用原生完整认知接纳时，先完成原生交付与确认，再生成 AOCX 投影及模型间视图。原生正文、receipt 和 attestation 按其契约处理，AOCX 转换结果只声明自己的转换与检查状态。

## 宿主流程

1. 根据 AOCI 规则选择读取范围，记录请求与源身份。
2. 收集该交付模式要求的完整结果；版本变化或缺失交付按原生规则处理。
3. 保存原文本/JSON 响应，声明完整快照或局部检索范围。
4. 原文件交给适配器；其他原始响应可生成 source/evidence 记录，并把完整响应放入 body。
5. 运行 AOCX 检查，为接收方选择完整、紧凑或经评估的语言视图。
6. 接收方据源身份回取详情；软件认知修改进入原生维护流程。

## MCP 载荷

MCP 工具可以提供 structuredContent 和文本块，工具自己的 outputSchema 规定返回结构。宿主可以在自己的结果、资源或独立适配工具内承载 AOCX，原有 AOCI 工具仍遵循原生 schema。

如需提供宿主适配工具，可使用一个入口加 operation 参数，按需资源承载大档案。常驻说明保持简短。对象形式 structuredContent 并附序列化文本可以覆盖所核对的 MCP 版本。初始交付的工具直接本地运行。

## 来源

- https://github.com/aoci-spec/aoci-code/blob/3d8e4b0048b7ae93d671ffae39db73a44db434d3/spec/public/aoci-mcp-runtime-v1.txt
- https://github.com/aoci-spec/aoci-code/blob/3d8e4b0048b7ae93d671ffae39db73a44db434d3/spec/public/aoci-overview-delivery-v1.txt
- https://modelcontextprotocol.io/specification/2025-11-25/server/tools
- https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/server/tools.mdx
