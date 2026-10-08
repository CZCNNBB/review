# 审批中心 Agent 配置与工具清单

> 状态：配置方案，尚未在 AI 平台创建 Agent 或 Tool。接入协议见 `backend/docs/AI平台与外部业务系统交互说明.md`；业务系统实现方案见同目录的《审批中心Agent接入方案.md》。

## 1. 需要配置几个 Agent

**共 3 个 Agent，挂在同一个 AI 业务平台下，全部启用普通多轮会话，不启用一次性对话。**

| 配置名 | 建议 Agent ID | 页面角色 | 能力边界 |
| --- | --- | --- | --- |
| 常态助手 | `approval-general` | 除下述详情页外的全站常态 Agent | 查询审批流、人员、部门、工作台任务等只读信息，解释列表结果 |
| 审批单助手 | `approval-summary` | 工作台审批详情和抄送详情的专属 Agent | 总结单据、节点和审批意见，回答追问，提供仅供参考的建议 |
| 流程设计助手 | `approval-flow-designer` | 审批流详情和版本编辑页的专属 Agent | 解释现有流程；在草稿编辑页生成、修改并校验候选流程 |

“子 Agent”在第一阶段指**页面根据路由直接选择专属 `agent_id`**，而不是先让常态 Agent 调用 AI 平台的 A2A 子 Agent。路由已明确知道当前对象，直接切换更可预测，也避免额外的一轮模型调度。三个 Agent 可复用同一模型、共用只读 Tool；提示词和 Tool 授权分别配置。以后确需跨场景自主委派时，再评估 AI 平台的 A2A 能力。

固定 `external_user_id = approval_admin` 由审批中心后端填写，前端不能提交或更改。三个 Agent 使用同一个 AI 业务平台 API Key，由后端保管。

## 2. 页面如何自动切换

| 当前路由 | 生效 Agent | 会话作用域 | 页面预设操作 |
| --- | --- | --- | --- |
| `/processes/:id` | 流程设计助手 | `process_id` | “解读这个审批流”；若存在草稿，可引导进入编辑页生成 |
| `/versions/:id` | 流程设计助手 | `version_id` | “AI 生成审批流”；只有 `DRAFT` 可预览并应用 |
| `/instances/:id` | 审批单助手 | `instance_id` | “AI 总结”；建议始终由人判断和操作 |
| `/copies/:id` | 审批单助手 | `copy_task_id`，并核对关联审批单 | “AI 总结”；保持只读 |
| 其他页面，包括工作台列表、流程列表和人员部门列表 | 常态助手 | 管理端全局 | 自由提问、查询列表 |

进入专属页面时，聊天面板自动切换**Agent 身份与当前对象的历史会话**，但不自动扣费发送消息。点击页面内快捷按钮才新建会话并发预设消息；用户也可以直接在面板输入。离开专属页面后恢复常态助手之前的会话。会话 ID 绑定 Agent、场景和对象；同一 Agent 在不同审批单或版本之间也不能串用会话。面板要明确显示当前 Agent 与对象，避免用户误以为仍在问上一张单据。

审批流详情与版本编辑是两个不同的对象作用域：在详情页打开某个草稿编辑器时，可在面板中提供“继续这条讨论”的显式入口，但只有后端确认 `version_id` 属于当前 `process_id` 才允许迁移上下文；第一版默认新开版本会话，避免隐式混用。

## 3. 最小 Tool 清单：9 个只读/校验工具

AI 平台将下面的业务 HTTP API 配置为 MCP Tool，并绑定到审批中心业务平台。工具请求统一落到 `app/server/ai/api` 提供的受控 AI Tool API；它们在服务端调用现有组织、流程、工作台领域服务，统一裁剪返回字段、限制分页和脱敏。**不直接把现有管理 API 的 `X-Admin-Key` 配到 AI 平台。**

| Tool 名称 | 输入 | 输出重点 | 授予 Agent |
| --- | --- | --- | --- |
| `search_processes` | 关键词、状态、页码、每页数量 | 流程 ID、名称、状态、当前版、草稿版、节点数 | 常态、流程设计 |
| `get_process_overview` | `process_id` | 流程详情、版本列表、草稿及发布状态 | 常态、流程设计 |
| `search_departments` | 关键词、页码、每页数量 | 部门 ID、名称、状态、层级/上级 | 常态、流程设计 |
| `list_department_members` | `department_id`、页码、每页数量 | 该部门的人员姓名、人员 ID、在职状态 | 常态、流程设计 |
| `search_persons` | 姓名/工号关键词、页码、每页数量 | 人员 ID、姓名、部门摘要、状态 | 常态、流程设计 |
| `search_work_items` | 人员 ID、任务类型、状态、页码、每页数量 | 审批/抄送任务、单据标题、当前状态和节点 | 常态 |
| `get_approval_context` | `instance_id`；抄送场景另带 `copy_task_id` | 已授权审批单的表单显示名与值、流转节点、审批意见、状态 | 审批单助手 |
| `get_flow_context` | `process_id` 或 `version_id` | 当前图、表单 Schema、启用节点定义/配置约束、可选审批人摘要、`revision` | 流程设计助手 |
| `validate_flow_proposal` | `version_id`、候选结构化提案 | 只读校验结果、逐项问题、可供预览的规范化候选图 | 流程设计助手 |

计划由 `app/server/ai/api` 暴露下列 HTTP 目标，再在 AI 管理平台逐项登记为 MCP Tool：

| Tool | HTTP 方法与目标路径 | 关键参数来源 |
| --- | --- | --- |
| `search_processes` | `GET /api/ai/tools/processes` | 关键词、分页来自 `tool` |
| `get_process_overview` | `GET /api/ai/tools/processes/{process_id}` | 流程 ID 来自 `tool`；流程详情页可用 `runtime` 锁定当前 ID |
| `search_departments` | `GET /api/ai/tools/departments` | 关键词、分页来自 `tool` |
| `list_department_members` | `GET /api/ai/tools/departments/{department_id}/members` | 部门 ID 来自 `tool` |
| `search_persons` | `GET /api/ai/tools/persons` | 姓名/工号关键词、分页来自 `tool` |
| `search_work_items` | `GET /api/ai/tools/work-items` | 人员 ID、类型、状态、分页来自 `tool` |
| `get_approval_context` | `GET /api/ai/tools/approval-context` | 审批单和抄送任务 ID 只来自可信 `runtime` |
| `get_flow_context` | `GET /api/ai/tools/flow-context` | 流程或版本 ID 只来自可信 `runtime` |
| `validate_flow_proposal` | `POST /api/ai/tools/flow-proposals/validate` | 版本 ID 来自 `runtime`；候选结构来自 `tool` |

这些是**拟新增的业务系统接口**，不是当前已经可调用的 URL；实施后才能在 AI 平台完成 Tool 的目标地址和发布。`runtime` 参数由审批中心后端在 `/agent/messages.inputs` 中生成，不能采用浏览器任意指定的 ID。所有列表 Tool 设置分页上限；校验 Tool 限制候选图的节点数和请求体大小。

列表 Tool 必须在后端做分页上限和返回字段裁剪；找不到记录时返回明确的空结果，不诱导模型编造。`get_approval_context` 不接收任意租户或人员 ID 来绕过对象访问校验。`validate_flow_proposal` **不保存草稿**；最终仍由用户确认，再调用现有草稿保存接口。流程设计助手可以复用人员查询 Tool 来消除“张三是哪位”的歧义，但人员 ID 必须经业务后端验证。

工具合计是**9 个独立定义**，不是每个 Agent 各配 9 个。常态助手挂前 6 个；审批单助手只挂 `get_approval_context`；流程设计助手挂 `search_processes`、`get_process_overview`、`search_departments`、`list_department_members`、`search_persons`、`get_flow_context`、`validate_flow_proposal`。流程设计助手需要组织工具，是为了根据自然语言选择真实审批人。工具授权遵循场景需要；三个 Agent 均不挂写操作 Tool。

第一版也可先让后端在每次调用时通过 `additional_system_context` 与 `inputs` 注入当前审批单或流程版本信息，再逐步发布专属查询 Tool；但常态助手的列表问答至少需要前 6 个 Tool，不能仅靠提示词回答实时业务数据。即便已注入页面上下文，专属 Tool 仍可用于追问时读取最新状态。

## 4. Tool 鉴权与 AI 平台配置

现有流程、组织列表使用管理端 `X-Admin-Key`。为了把 Tool 权限控制在只读/校验范围，在 `app/server/ai/api` 增加单独的 AI Tool 路由和独立的 `AI_TOOL_KEY`；后端用常量时间比较校验 `X-AI-Tool-Key`。这些路由只开放上表列出的数据和操作，不接受任意目标 URL 或任意 SQL。

按 AI 平台文档的运行时凭证机制，审批中心后端调用 `/agent/messages` 时可把专用 Tool 凭证放入 `X-Business-Authorization`；各 Tool 配置 `business_token_header = X-AI-Tool-Key`，由 FastMCP 原样透传。该凭证只用于 AI Tool API，不是管理端 `X-Admin-Key`，不得写进 Tool 固定请求头、前端或日志。AI 平台和审批中心之间使用内网 HTTPS，Tool API 不直接暴露公网。若平台要求 `Bearer` 格式，后端和 Tool 校验器必须明确采用同一格式；平台不会替我们增删前缀。

每个 Tool 在 AI 管理平台配置目标 URL、HTTP 方法、参数来源 `tool` / `runtime` / `static`、超时、输出 Schema 与平台绑定，并先测试再发布。对象 ID 等可信上下文放在运行时 `inputs`，后端对 Tool 请求仍须核对会话绑定；模型生成的查询参数只用于受限筛选。不要让模型决定 Tool 的目标服务器地址。

本期 Agent 配置：

| Agent | 系统提示词重点 | 可用 Tool | 额外开关 |
| --- | --- | --- | --- |
| 常态助手 | 先查再答；回答附对象名称和状态；无结果明确说明 | 6 个列表/详情 Tool | 多轮会话；第一版不需要 A2A、知识库、表单中断 |
| 审批单助手 | 区分事实、待确认点与建议；引用当前单据和流转记录；绝不执行审批 | `get_approval_context` | 多轮会话；抄送场景固定只读 |
| 流程设计助手 | 只用真实节点类型/人员；产出可校验的候选图；说清未决条件 | 7 个流程/组织/校验 Tool | 多轮会话；结构化提案输出；不自动保存、发布 |

## 5. 与现有接口的对应关系

AI Tool API 作为适配层复用以下已有能力，不需要在 `process` 或 `organization` 模块复制业务规则：

| Tool 范围 | 现有能力 |
| --- | --- |
| 流程与版本查询 | `/api/admin/processes`、`/api/admin/processes/{process_id}`、版本列表、`/api/admin/process-versions/{version_id}/graph` |
| 人员部门查询 | `/api/admin/persons`、`/api/admin/departments`、部门人员列表 |
| 工作台任务查询 | `/api/work-items`，支持人员、类型和状态筛选 |
| 审批单上下文 | 审批实例详情、抄送任务关联审批单查询、版本表单 Schema |
| 流程提案校验 | 现有 `process_validation.py` 和节点定义；保存仍走带 `revision` 的整图保存服务 |

部分现有列表接口只有分页、没有关键词检索。对应 Tool 的关键词过滤或受限搜索需要在 AI 适配层或原领域服务补齐，不能把第一页结果当成全量数据来回答“有没有某个人”。

## 6. 会话、回答和发布边界

- 所有 Agent 都是普通会话；第一次 `conversation_id = null`，后续传回同一个 ID。历史由 AI 平台保存，本地仅保存 Agent、场景与对象绑定。
- 常态助手的会话作用域是固定管理员；所有具备管理密钥的操作员目前共享该历史。这与用户选择的固定管理员 ID 一致，后续接入个人登录需重新隔离。
- 切换页面不重发上一条消息，也不把常态助手会话自动续到专属 Agent。专属页面的快捷按钮每次新开会话并发送预设问题。
- Agent 输出中的审批建议只供阅读；审批接口不作为 Tool。流程提案必须经过解析、结构校验、预览及人工应用；保存和发布接口不作为 Tool。
- AI 平台的 SSE 至少处理 `run_start`、`model_delta`、`run_end`、`error`；历史消息通过 `structured_content` 回放。实际字段位置以联调样例确认。

## 7. 配置与验收清单

1. 在 AI 管理平台创建 **1 个业务平台、1 把平台 API Key、3 个 Agent、9 个 Tool**；将 Tool 按上表挂载给 Agent。
2. 审批中心后端配置平台地址、平台 API Key、3 个 Agent ID、固定管理员 ID 和独立 Tool 凭证；所有配置留在服务端。
3. 常态助手在流程列表、人员部门页面可以查实时数据，跨普通页面继续同一会话。
4. 进入 `/processes/:id`、`/versions/:id`、`/instances/:id`、`/copies/:id` 时准确切换 Agent 与对象会话；退出后恢复常态助手。
5. 同名人员、空列表、分页超限、对象不存在、抄送任务与单据不匹配时，Tool 返回可解释错误或空结果，不编造信息。
6. 审批单助手无法调用审批决策接口；流程设计助手无法调用保存或发布接口；未通过校验的提案不能应用。
7. AI 平台 API Key、Tool 凭证、管理密钥不会出现在浏览器、URL、日志或 AI 平台 Tool 固定请求头中。

**实施前需从 AI 平台确认**：A2A 是否有必须使用的产品约束；结构化输出的实际能力；SSE、Tool 结果和历史消息的真实响应样例。本方案第一版按“前端路由直接切换三个 Agent”实施，不依赖 A2A。
