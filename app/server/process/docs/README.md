# 审批流维护模块实现说明

本文件记录审批流维护模块（`app/server/process`）的落地细节。设计方案见同目录下的
`审批流模块设计.md`，本文件只补充实现层面的约定和容易踩坑的地方。

> 实现状态：节点能力管理、流程定义管理、节点与编排管理已落地。
> 租户流程授权（`tenant.process_binding`）按约定推迟到租户模块后续版本实现。

## 1. 模块边界

本模块只负责**定义态**：维护审批流的当前定义、节点实例和编排关系。

不负责运行态。审批实例、运行快照、待办任务和流程推进属于后续的审批运行模块，
业务动作回调属于回调执行模块。保存流程不会影响已经创建的审批实例，因为运行模块
会在发起时保存自己的运行快照。

## 2. 代码结构

```text
app/server/process/
├── api/
│   ├── __init__.py                 API 聚合出口
│   ├── node_definition_api.py      节点能力定义接口
│   └── process_api.py              流程主体、编排、启停和校验接口
└── src/
    ├── constants.py                枚举取值、条件操作符规则、校验规则码
    ├── models/process_model.py     三张表的 SQLModel 定义
    ├── schemas/                    请求与响应模型
    ├── repository/                 数据访问层
    ├── service/
    │   ├── exceptions.py            领域异常
    │   ├── node_definition_service.py
    │   ├── process_service.py       整图保存事务、复制、状态迁移
    │   └── process_validation.py    完整性校验引擎（纯逻辑）
    └── utils/json_schema.py         JSON Schema 校验与中文错误映射
```

校验引擎不访问数据库：节点定义和审批人状态由 Service 批量查询后作为参数传入。
所有校验函数返回问题列表而不是抛首个错误，管理页面才能一次性展示全部问题。

## 3. seed 节点定义

`data/init.sql` 用固定 UUID 注册了三个节点能力定义，前端画布和联调环境可以稳定引用：

| node_type | UUID | 名称 |
|---|---|---|
| START | `00000000-0000-0000-0000-000000000101` | 开始 |
| APPROVAL | `00000000-0000-0000-0000-000000000102` | 人工审批 |
| END | `00000000-0000-0000-0000-000000000103` | 结束 |

seed 使用 `ON CONFLICT (id) DO NOTHING` 保证重复执行安全。审批和结束节点的配置
规则声明在 `config_schema_json` 中，后端直接用它校验节点实例的 `config_json`，
因此**新增节点能力只需要新增一条节点定义，不需要改后端代码**，前提是 `node_type`
必须是后端已经实现执行器的类型（START、APPROVAL、END）。

## 4. JSON 字段写入约束

三张表的 JSON 列在 PostgreSQL 上落 `JSONB`。模型里声明为
`JSON().with_variant(JSONB(), "postgresql")`，原因是租户模块和人员组织模块的测试
仍在 SQLite 上用 `SQLModel.metadata` 建表，SQLite 无法渲染 JSONB。

**所有 JSON 字段更新必须整体重新赋值，禁止原地修改。** SQLAlchemy 只在属性被显式
赋值时才把该列放进 UPDATE 的 SET 子句，下面这种写法会静默丢失改动：

```python
node.config_json["approval_mode"] = "OR"      # 错误：不会被写入数据库
node.config_json = {**node.config_json, "approval_mode": "OR"}   # 正确
```

`tests/test_process_service.py::test_in_place_json_mutation_is_not_persisted`
把这条约束钉死了。复制流程时必须 `deepcopy`，否则源流程与副本会在同一个会话里
共享同一批字典对象。

另外 JSON 里不能放 `UUID` 或 `datetime` 对象，节点 ID 和 `person_id` 一律存字符串。

## 5. 整图保存

`PUT /admin/processes/{process_id}/graph` 是唯一的整图写入口，在一个事务中完成：

1. 读取流程主体，不存在返回 404。
2. 批量查询节点定义，缺省的表单字段沿用流程原值。
3. 批量查询审批人状态。
4. **写前全量校验**，不通过直接返回 422，此时数据零写入。
5. 写入节点：先删除本次已移除的节点并 `flush`，再拦截「节点 ID 已被其它流程占用」
   的请求（返回 409），最后逐个新增或更新。
6. 保存编排与流程主体。
7. `flush` 后按落库状态复核一次，不通过则整体回滚。
8. 提交事务。

`get_postgres_engine` 只负责提供会话，不会自动提交或回滚，事务由 Service 自己管理。

编排写入时会按 `source_node_id`、`target_node_id`、`condition`、`default` 重建，
前端传入的其它键不会入库，避免存下运行时不认识的结构。读取时只认 `connections`，
其它键忽略，为将来扩展留出兼容空间。

## 6. 校验规则码

`src/constants.py` 定义了全部规则码，前端可以按 `code` 定位到画布元素，按 `node_id`
和 `field` 定位到具体配置项。

| 分类 | 规则码 |
|---|---|
| 编排结构 | `ORCHESTRATION_INVALID` |
| 节点定义 | `NODE_DEFINITION_NOT_FOUND`、`NODE_DEFINITION_DISABLED`、`NODE_TYPE_UNSUPPORTED` |
| 节点配置 | `NODE_CONFIG_INVALID` |
| 审批人 | `APPROVAL_MODE_INVALID`、`APPROVER_REQUIRED`、`APPROVER_ID_INVALID`、`APPROVER_DUPLICATE`、`APPROVER_NOT_FOUND`、`APPROVER_DISABLED` |
| 开始结束 | `START_COUNT_INVALID`、`END_REQUIRED`、`END_APPROVED_REQUIRED`、`END_RESULT_STATUS_INVALID` |
| 连线端点 | `CONNECTION_NODE_UNKNOWN`、`START_AS_TARGET`、`END_AS_SOURCE` |
| 拓扑 | `NODE_UNREACHABLE`、`NODE_WITHOUT_OUTGOING`、`GRAPH_CYCLE` |
| 条件分支 | `CONNECTION_CONDITION_REQUIRED`、`CONNECTION_DEFAULT_REQUIRED`、`CONNECTION_DEFAULT_DUPLICATE`、`CONNECTION_DEFAULT_WITH_CONDITION`、`CONNECTION_CONDITION_INVALID`、`CONNECTION_FIELD_UNKNOWN`、`CONNECTION_OPERATOR_INCOMPATIBLE`、`CONNECTION_VALUE_NOT_IN_ENUM` |

### 6.1 实现时的几点取舍

- 设计文档里「所有非 END 节点至少存在一条后续连接」和「不允许没有出口的死节点」
  是同一件事，合并为一条 `NODE_WITHOUT_OUTGOING`，避免同一问题报两次。
- 可达性只有在恰好存在一个开始节点时才检查，否则会产生满屏无意义的不可达报错。
  环检测不受影响，对全部节点执行，不可达分量里的环同样会报出来。这两项必须分开
  计算：用一张颜色表同时表达可达性和是否有环会漏掉不可达分量中的环。
- 条件字段不存在时不再继续做操作符兼容判断，避免级联报错。
- 节点定义缺失或类型不受支持的节点不参与开始、结束和拓扑规则，只报定义本身的错误。

### 6.2 比设计文档更严的两条规则

设计文档 §12 没有列出下面两条，但缺少它们会产生无法工作的流程，因此一并实现：

- `END_APPROVED_REQUIRED`：至少需要一个 `result_status` 为 `APPROVED` 的结束节点。
  只有拒绝出口的流程永远无法成功。
- `CONNECTION_VALUE_NOT_IN_ENUM`：条件取值必须落在字段的 `enum` 范围内。枚举外的
  取值永远不会命中，属于配置错误而不是运行时问题。

### 6.3 有意未加入的规则

同一来源存在多条连线时，**不要求**必须有一条默认路径。设计文档 §10 把默认路径
描述为可选项（「最多配置一条默认连接」）。需要注意：如果所有条件都未命中且没有
默认路径，流程会在该节点停住。审批运行模块实现分支推进时需要处理这种情况。

## 7. 流程状态

| 迁移 | 触发接口 | 规则 |
|---|---|---|
| → DRAFT | `POST /admin/processes` | 创建恒为草稿，创建请求不接收 status |
| DRAFT / DISABLED → ENABLED | `POST .../enable` | 必须通过完整校验 |
| ENABLED → ENABLED | `POST .../enable` | 幂等，不重复校验 |
| ENABLED / DISABLED → DISABLED | `POST .../disable` | 不需要校验，已停用时幂等 |
| DRAFT → DISABLED | `POST .../disable` | 拒绝，返回 409 |
| 任意 → 删除 | 无 | 不提供删除接口，废弃流程置 DISABLED |

校验触发点：`PUT /graph`、带表单的 `PATCH`、`POST /enable`、`POST /validate` 执行
完整校验；`POST /processes` 只校验表单 Schema 结构（此时还没有节点）；复制、停用和
改名称不执行完整校验。

启用中的流程仍允许编辑：按设计文档 §1，修改只影响之后新发起的审批实例。

## 8. 接口清单

```text
POST   /api/admin/node-definitions                              创建节点能力定义
GET    /api/admin/node-definitions                              查询节点能力定义列表
GET    /api/admin/node-definitions/{node_definition_id}         查询节点能力定义详情
PATCH  /api/admin/node-definitions/{node_definition_id}         更新节点能力定义

POST   /api/admin/processes                                     创建审批流
GET    /api/admin/processes                                     查询审批流列表
GET    /api/admin/processes/{process_id}                        查询审批流详情
PATCH  /api/admin/processes/{process_id}                        更新审批流资料与表单
POST   /api/admin/processes/{process_id}/copy                   复制审批流
POST   /api/admin/processes/{process_id}/enable                 启用审批流
POST   /api/admin/processes/{process_id}/disable                停用审批流
GET    /api/admin/processes/{process_id}/graph                  读取流程编排
PUT    /api/admin/processes/{process_id}/graph                  保存流程编排
POST   /api/admin/processes/{process_id}/validate               校验流程完整性
```

全部接口使用 `X-Admin-Key` 管理密钥（环境变量 `APPROVAL_ADMIN_KEY`），响应统一为
`Result` 包装。校验失败返回 422，`detail` 形如：

```json
{
  "message": "流程校验未通过，请修正后重新保存",
  "issues": [
    {
      "code": "NODE_WITHOUT_OUTGOING",
      "message": "节点「财务审批」没有任何后续连线，流程会在此中断",
      "node_id": "…",
      "field": null,
      "connection_index": null
    }
  ]
}
```

`POST /validate` 用 200 加 `valid` 字段表达校验结果，问题结构相同，供设计器的
「检查」按钮使用。

列表响应包含 `node_count`。设计文档 §15 还要求展示「已授权租户数量」，该字段要等
`tenant.process_binding` 落地后再补，本轮不返回恒为 0 的占位字段。

## 9. 测试

```powershell
cd D:\work\DaiJun\ZhiHuiBan\ShenPi\backend
python -m unittest discover -s tests -v
```

- `tests/test_process_validation.py`：校验引擎全部规则，纯函数，不需要数据库。
- `tests/test_init_sql.py`：初始化脚本的可拆分性和 seed 数据，不需要数据库。
- `tests/test_node_definition_service.py`、`tests/test_process_service.py`、
  `tests/test_process_api.py`：需要可用的 PostgreSQL 数据库。表结构由人工在数据库
  客户端执行 `backend/data/init.sql` 建立，应用代码不包含建库动作。

数据库测试只清理自己在测试期间显式登记的记录，不会按名称或范围批量删除。
`tests/process_test_helpers.py` 提供 seed 解析和会话清理能力，校验测试直接使用
`init.sql` 里注册的配置 Schema，避免测试和生产的规则漂移。

## 10. 本轮未实现

- `tenant.process_binding` 表、租户授权接口和发起审批前的租户访问校验，按约定推迟
  到租户模块后续版本。
- 审批实例、运行快照、待办任务、审批操作和业务回调。
- 显式流程版本管理、顺序审批、图级并行、环路与退回重审、脚本条件、动态选人、
  加签转交、子流程和定时器节点。
