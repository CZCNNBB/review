# 审批流定义模块实现说明

本文件记录 app/server/process 已落地的实现约定。完整定义方案见
《审批流模块设计》，后续运行方案见《审批流运行模块设计》。

> 实现状态：节点能力、流程主体、显式版本、版本节点、整图校验、草稿复制和发布已完成。
> 审批实例、任务和执行引擎尚未实现。

## 1. 当前模块边界

process 最终统一承载审批流定义和审批运行，当前代码只实现定义部分：

- node_definition 描述公共节点能力。
- approval_process 保存稳定流程 ID、启停状态和当前发布版本。
- approval_process_version 保存每一版表单和编排。
- approval_process_version_node 保存每一版具体节点和冻结配置。

业务系统以后只传稳定的 process_id。运行模块会读取 current_version_id 并把版本 ID
绑定到审批实例，不再为每个实例保存完整流程快照。

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
- 恰好一个开始节点，至少一个结束节点和一个审批通过出口。
- 连线端点有效，全部节点可达，非结束节点有出口。
- 第一版流程图无环。
- 存在条件连线时具有唯一默认路径。
- 条件字段、操作符和值与审批表单 Schema 匹配。

节点内部多人审批只支持 AND 和 OR。两种模式都是任意一人拒绝即拒绝；执行语义将在
后续运行模块中实现。

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

## 7. 测试

~~~powershell
cd D:\work\DaiJun\ZhiHuiBan\ShenPi\backend
python -m unittest discover -s tests -p "test_*.py" -v
~~~

数据库集成测试要求先执行对应的初始化或升级 SQL。测试只清理自己明确登记的数据。

## 8. 尚未实现

- tenant.process_binding 和租户流程授权接口。
- 审批实例、节点执行、待办任务和审批记录。
- 审批执行引擎和业务回调。
- 顺序审批、图级并行、退回重审、动态选人、加签转交、子流程和定时器节点。
