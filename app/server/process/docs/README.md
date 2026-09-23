# 审批流模块实现说明

本文件记录 app/server/process 已落地的实现约定。定义方案见《审批流模块设计》，
运行方案见《审批流运行模块设计》，审批通过后的调用方案见《业务执行模块设计》。

> 实现状态：定义层（节点能力、流程主体、显式版本、版本节点、整图校验、草稿复制和发布）
> 和运行层（审批实例、节点执行、待办任务、审批记录、执行引擎、发起与审批接口）已完成。
> 租户流程授权和租户使用记录已经实现；业务执行子模块已完成设计、尚未开发。

## 1. 当前模块边界

process 统一承载审批流定义、审批运行和审批通过后的业务执行，定义层包含：

- node_definition 描述公共节点能力。
- approval_process 保存稳定流程 ID、启停状态和当前发布版本。
- approval_process_version 保存每一版表单和编排。
- approval_process_version_node 保存每一版具体节点和冻结配置。

运行层包含：

- approval_instance 保存审批单数据、业务执行参数和实例状态。
- approval_node_execution 保存实例实际经过的节点和实际选择的路径。
- approval_task 保存人工审批节点为每位审批人创建的待办。
- approval_record 保存审批人的实际操作，是不可修改的审计记录。

业务系统只传稳定的 process_id。发起审批时读取 current_version_id，并把版本 ID 绑定到
审批实例，不再为每个实例保存完整流程快照。

## 2. 版本生命周期

1. 创建流程时同步创建 V1 草稿，revision 为 0。
2. 草稿整图保存成功后 revision 加一。
3. 发布时执行完整校验，把版本改为 PUBLISHED，并原子切换流程的 current_version_id。
4. 已发布版本永久只读。
5. 再次编辑时，从当前发布版本复制下一版草稿，并为所有节点生成新 UUID。
6. 新版本发布前，当前发布版本继续有效。

数据库通过 (process_id, version_no) 唯一约束和“每条流程最多一个草稿”的部分唯一
索引兜底。Service 使用行锁和 revision 防止并发保存、发布和草稿创建互相覆盖。

## 3. 整图保存

PUT /api/admin/process-versions/{version_id}/graph 是整图唯一写入口。请求必须携带读取时
获得的 revision。后端在一个事务中完成：

1. 锁定目标版本并确认仍为草稿。
2. 比较请求和数据库修订号，不一致返回 409。
3. 批量查询节点定义和审批人。
4. 完整校验节点、审批人、拓扑、条件和默认路径。
5. 增删改版本节点，并固化每个节点的 node_type。
6. 保存版本表单和编排，把 revision 加一。
7. 按会话中的落库状态复核一次。
8. 提交事务。

所有 JSON 字段必须整体重新赋值，禁止原地修改。SQLAlchemy 默认不会侦测普通字典的
原地变化。

## 4. 校验边界

草稿保存和发布至少校验：

- 节点定义存在、启用且执行类型受支持。
- 节点配置符合节点定义 JSON Schema。
- 审批人存在、启用且没有重复。
- 恰好一个开始节点，至少一个结束节点（走到结束节点就是审批通过）。
- 连线端点有效，全部节点可达，非结束节点有出口。
- 第一版流程图无环。
- 存在条件连线时具有唯一默认路径。
- 条件字段、操作符和值与审批表单 Schema 匹配。

节点内部多人审批只支持 AND 和 OR，两种模式都是任意一人拒绝即拒绝。执行语义由运行层
的引擎实现，见第 10 节。

## 5. 接口清单

~~~text
POST   /api/admin/node-definitions
GET    /api/admin/node-definitions
GET    /api/admin/node-definitions/{node_definition_id}
PATCH  /api/admin/node-definitions/{node_definition_id}

POST   /api/admin/processes
GET    /api/admin/processes
GET    /api/admin/processes/{process_id}
GET    /api/admin/processes/{process_id}/versions
POST   /api/admin/processes/{process_id}/draft
POST   /api/admin/processes/{process_id}/copy
POST   /api/admin/processes/{process_id}/disable

GET    /api/admin/process-versions/{version_id}/graph
PUT    /api/admin/process-versions/{version_id}/graph
POST   /api/admin/process-versions/{version_id}/validate
POST   /api/admin/process-versions/{version_id}/publish
~~~

全部管理接口使用 X-Admin-Key。流程列表和详情同时返回当前版本、草稿版本及画布节点
数量，前端可以直接判断进入查看模式还是编辑模式。

## 6. 数据库脚本

- 全新数据库执行 backend/data/init.sql。
- 已经创建过旧三表结构且流程表为空时，执行
  backend/data/migrations/20260921_process_version_upgrade.sql。

升级脚本会先检查 process.approval_process 是否为空。只要发现数据就中止，不会删除
已有流程。该脚本是一次性升级脚本；成功执行后不要重复执行。

新增审批运行表后，已有开发库只需重新执行一次 init.sql 即可补齐，四张运行表都是
新建表，不需要单独的升级脚本。

## 7. 测试

~~~powershell
cd D:\work\DaiJun\ZhiHuiBan\ShenPi\backend
python -m unittest discover -s tests -p "test_*.py" -v
~~~

数据库集成测试要求先执行对应的初始化或升级 SQL。测试只清理自己明确登记的数据。
运行层测试额外覆盖幂等发起、AND 与 OR 决策、条件分支、审批记录只写一次以及两人
同时审批同一实例时的行锁行为。

## 8. 发起审批

POST /api/processes/{process_id}/instances 的处理顺序：

1. 用“流程 + 业务单据标识”生成内部幂等键，命中已有实例时直接返回，不重复创建。
2. 锁定流程主体，确认状态为 ENABLED 并读取 current_version_id。
3. 读取该版本的节点，组装运行期视图。
4. 按版本表单 Schema 校验 approval_form，校验发起人存在且启用。
5. 创建审批实例并绑定确定版本。
6. 从开始节点推进，直到进入人工审批节点或结束。
7. 在同一个事务中提交实例、节点执行记录和首批任务。

幂等键是租户、流程和业务单据标识的 SHA-256 摘要，长度固定且可以安全重复生成。
实例同时保存发起请求内容的规范化摘要（`request_digest`），重放时比对：内容一致返回
原实例并标记 idempotent_replay，内容已经变化返回 409 并提示改用新的业务单据标识。
审批单数据、业务执行参数、业务动作、标题或发起人任一变化都会触发冲突，避免新的
内容被静默忽略后继续使用旧的执行参数。

并发提交相同幂等键时由唯一约束决出胜负，失败的一方比对摘要后返回已有实例。

## 9. 执行引擎

engine 包按节点类型分发，已注册的处理器与节点定义中的 node_type 一一对应：

~~~text
START      进入后立即完成，按编排选择后续节点
CONDITION  进入后立即按出线条件选路，不产生人工任务
APPROVAL   为全部审批人同时创建 PENDING 任务，实例停在该节点
END        把实例置为 APPROVED（走到这里就是审批通过）、记录结束时间
~~~

推进入口是引擎内部的单次循环：进入节点、交给处理器、处理器返回下一个节点 ID 或
None。None 表示流程需要等待人工处理。已发布版本禁止成环，循环仍然保留步数上限，
防止编排数据被写坏时把请求拖死。

条件选择按编排数组顺序取第一条命中的条件连线，全部未命中时使用默认路径。条件字段
统一以 approval_form 前缀定位，支持嵌套路径；字段缺失按空值处理，除 IS_EMPTY 外都
不命中，避免条件引用了一个并不存在的字段却静默生效。

大小比较按字段类型选择方式：数字按数值比较；`date`、`date-time`、`time` 字段按表单
Schema 声明的 format 解析后比较，`date-time` 统一换算到 UTC，缺少时区的取值按 UTC
解释。合法但时区或写法不同的时间字符串字典序与真实顺序可能相反，直接比较字符串会
选错分支，因此解析失败时一律按不命中处理。运行期视图 `VersionGraph.field_formats`
保存了这份字段格式表。

审批通过后推进失败时（例如版本编排被破坏），实例和当前节点会置为 ERROR 并取消
待处理任务，已提交的审批记录保持不变，后台可以按 ERROR 状态排查异常实例。

## 10. 多人审批与并发控制

- AND：全部任务同意后节点通过。
- OR：第一个同意结果决定节点通过，其余待办取消。
- 两种模式任意一人拒绝都立即拒绝整个实例，其余待办同时取消。

审批操作在一个事务中完成：锁定实例、锁定任务、校验状态、写审批记录、更新任务、
按模式判断节点结果、取消多余待办、完成节点并推进。

锁定实例行把同一实例上的并发操作串行化，保证 OR 模式只形成一个最终结果。重复提交
相同结果时返回原结果并标记 idempotent_replay，不重复写记录；任务已经被其他结果
处理或取消时返回 409。

## 11. 运行接口

~~~text
POST /api/processes/{process_id}/instances              发起审批
GET  /api/approval-instances/{instance_id}              查询审批详情
GET  /api/approval-instances/{instance_id}/timeline     查询运行时间线
GET  /api/approval-tasks?person_id=&status=             查询人员待办或已办
POST /api/approval-tasks/{task_id}/approve              同意任务
POST /api/approval-tasks/{task_id}/reject               拒绝任务
~~~

审批详情返回当前节点、节点耗时、待办人员和审批记录；时间线按实际执行顺序返回经过
的节点，并在每个节点下挂上该节点产生的任务和审批记录。耗时统一由查询接口按时间
字段计算，运行表不保存冗余的耗时字段：节点取 `completed_at - entered_at`，任务取
处理时刻减任务产生时间，被取消的任务取 `cancelled_at`，避免已结束的耗时继续增长。

接入项目平台登录身份前，任务查询和审批请求显式传递 person_id，接口层校验任务确实
分配给了该人员，否则返回 403。审批单数据用于展示，execution_payload 只供审批通过后
的业务动作使用，不通过详情接口返回。

## 12. 尚未实现

- 审批通过后创建 `process.business_execution_record`，以及提交后的业务接口调用。
- 运行表的统计汇总表或物化视图。
- 顺序审批、图级并行、退回重审、动态选人、加签转交、子流程和定时器节点。
