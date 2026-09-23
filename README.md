# 审批中心 Backend

这是审批中心使用的 FastAPI 后端脚手架。当前采用“微服务预备架构”：所有服务先放在一个 FastAPI 项目中运行，但每个服务模块都拥有独立的 `api` 接口层和 `src` 业务逻辑层，后续可以按需拆成真正的独立微服务。

数据库采用“每个 server 一个 PostgreSQL Schema”的约定。当前租户服务使用 `tenant` Schema，人员与组织服务使用 `organization` Schema，审批流定义和运行统一使用 `process` Schema。

## 设计文档

- `docs/审批中心整体设计.md`：系统边界、模块划分、核心链路和实施顺序。
- `docs/项目开发初步进度记录表.md`：各模块设计、开发状态、目标和推荐实施节奏。
- `app/server/tenant/docs/租户模块设计.md`：已经完成的租户模块设计。
- `app/server/tenant/docs/租户作用域设计.md`：可选租户模式、TenantScope 和分表资源绑定设计。
- `app/server/organization/docs/人员与组织模块设计.md`：人员、部门及已经落地的租户解耦设计。
- `app/server/process/docs/审批流模块设计.md`：节点能力、流程编排、审批人和租户使用权设计。
- `app/server/process/docs/审批流运行模块设计.md`：显式版本、审批实例、节点执行、任务和审批记录设计。
- `app/server/process/docs/业务执行模块设计.md`：审批通过后的单次业务调用、Service Token 和执行记录设计。
- `app/server/process/docs/README.md`：审批流维护模块的实现说明，包含种子节点定义、校验规则码和 JSON 字段写入约束。
- `app/server/integration/docs/业务接入模块设计.md`：业务动作、租户授权、审批使用记录和发起审批事务设计。
- `app/server/integration/docs/业务接入接口说明.md`：业务接入接口清单、API Key 使用方式、错误码和联调步骤。
- 其他模块的设计文档统一存放在各自 `app/server/<module>/docs/` 下。

## 项目结构

```text
backend/
  app/
    main.py                       # FastAPI 应用创建与路由注册
    bootstrap.py                  # 启动初始化

    common/                       # 跨服务公共能力
      config/                     # 全局配置
      db/                         # 数据库连接
      schemas/                    # 通用响应模型
      scope/                      # 与租户实现无关的资源作用域与回调配置接口
      security/                   # 通用管理认证依赖

    server/                       # 后端服务模块集合
      tenant/
        api/                      # 租户管理与 API Key 认证接口
        src/
          models/                 # 租户、API Key、回调凭据模型
          schemas/                # 请求响应模型
          repository/             # 数据访问层
          service/                # 租户与凭据业务逻辑
          scope/                  # 租户资源过滤、校验与绑定实现
          utils/                  # API Key 生成和回调凭据加密工具

      organization/
        api/                      # 人员、部门和租户绑定管理接口
        docs/                     # 人员与组织模块文档
        src/                      # 独立的人员与组织业务逻辑

      process/                    # 审批流定义、版本、审批运行与通过后的业务执行
        api/
        docs/
        src/
          execution/              # 业务执行子模块：通用 HTTP 执行器和后台 Worker

      integration/                # 业务动作与接入配置
        api/
        docs/
        src/

```

## 分层约定

每个服务模块遵循同一套边界：

```text
api/     对外 API 接口层，只处理请求参数、响应包装、依赖注入
src/     服务内部业务逻辑、数据库操作、模型和工具
common/  多个服务都会用到的公共能力
```

例如租户服务：

```text
app/server/tenant/api/tenant_api.py
app/server/tenant/src/schemas/tenant_schema.py
app/server/tenant/src/models/tenant_model.py
app/server/tenant/src/repository/tenant_repository.py
app/server/tenant/src/service/tenant_service.py
app/server/tenant/src/utils/credential.py
```

## 启动方式

安装依赖：

```powershell
cd D:\work\DaiJun\ZhiHuiBan\ShenPi\backend
pip install -r requirements.txt
```

启动服务：

```powershell
python -m app.main
```

也支持进入 `app` 目录后直接启动：

```powershell
cd app
python main.py
```

也可以直接使用 uvicorn：

```powershell
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8090 --reload
```

### 环境变量

现有 `.env` 已按审批中心需求重置。开发前填写 PostgreSQL 配置：

```text
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=你的数据库密码
POSTGRES_DATABASE=approval_center
FASTAPI_HOST=127.0.0.1
FASTAPI_PORT=8090
TENANCY_ENABLED=true
```

租户管理接口使用临时管理密钥，后续接入项目平台管理员身份后替换：

```text
APPROVAL_ADMIN_KEY=请使用高强度随机值
```

业务系统提供的回调 Service Token 需要使用应用主密钥加密保存。可以执行：

```powershell
python -B -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

将结果写入：

```text
APPROVAL_CREDENTIAL_MASTER_KEY=生成的Fernet密钥
```

不要将实际密钥提交到代码仓库。

业务执行 Worker 在应用进程内轮询待执行记录并调用业务系统接口，参数全部通过环境变量控制：

```text
BUSINESS_EXECUTION_WORKER_ENABLED=true          是否启动 Worker，默认 true
BUSINESS_EXECUTION_POLL_INTERVAL_SECONDS=2      没有任务时的轮询等待秒数，必须大于 0
BUSINESS_EXECUTION_BATCH_SIZE=10                单次最多领取的记录条数，必须是正整数
BUSINESS_EXECUTION_CONCURRENCY=5                单进程同时执行的请求数，必须是正整数且不能大于批量数量
```

配置不合法时应用直接启动失败并指明具体环境变量。`BUSINESS_EXECUTION_WORKER_ENABLED=true`
时必须配置 `APPROVAL_CREDENTIAL_MASTER_KEY`，否则同样启动失败，避免应用正常运行却让每一条
执行记录都在解密阶段失败。

`BUSINESS_EXECUTION_WORKER_ENABLED=false` 时审批通过仍然创建 `PENDING` 执行记录，只是当前
进程不领取任务，适用于只提供 API 的进程或后续部署独立 Worker 的场景。多个进程同时启用时，
总并发量约等于进程数乘以单进程并发配置，重复领取由 PostgreSQL 的 `FOR UPDATE SKIP LOCKED` 兜住。

服务正常关闭时，Worker 会立即停止领取新任务，等待当前进程已经领取为 `RUNNING` 的任务保存
最终结果后再关闭连接；尚未领取的任务保持 `PENDING`。部署环境的停止宽限期需要大于业务动作
允许的最大 HTTP 超时时间，并为最终数据库写入预留时间。

### 初始化数据库表

数据库结构统一维护在：

```text
backend/data/init.sql
```

该文件是数据库结构的唯一来源，应用代码不包含任何建库动作。首次接入或结构有更新时，
在 PostgreSQL 客户端（psql、pgAdmin 或 IDE 的数据库工具）里连接目标数据库，执行
该文件的全部内容。脚本中所有语句都是幂等的，可以重复执行，不会影响已有数据。

新增模块时向该文件追加 Schema、表、外键、索引和 `COMMENT` 注释，保持注释与结构一致。
正式环境出现结构变更后应引入数据库迁移工具，`init.sql` 继续负责全新环境首次建库。

旧审批流三表结构为空时，执行下面的一次性升级脚本切换到显式版本结构：

```text
backend/data/migrations/20260921_process_version_upgrade.sql
```

脚本会先检查旧流程主体表是否为空，发现数据会主动中止。

`tenant.tenant_callback_credential` 由早期 HMAC 签名凭据升级为 Service Token 结构时，执行：

```text
backend/data/migrations/20260922_callback_credential_service_token.sql
```

脚本会先检查是否存在 `ACTIVE` 凭据，发现有效凭据会主动中止，需要先撤销再执行。全新库由
`init.sql` 直接创建 Service Token 结构，不需要执行本脚本。

结束节点去掉「结束状态」配置（走到结束节点就是审批通过、流程完成）时，执行：

```text
backend/data/migrations/20260924_end_node_without_result_status.sql
```

脚本只更新 END 种子定义的 Schema 和说明，可重复执行。全新库由 `init.sql` 直接写入清理后的
内容，不需要执行本脚本。

## 当前接口

```text
GET  /
POST /api/admin/tenants
GET  /api/admin/tenants
GET  /api/admin/tenants/{tenant_id}
PATCH /api/admin/tenants/{tenant_id}
POST /api/admin/tenants/{tenant_id}/api-keys
GET  /api/admin/tenants/{tenant_id}/api-keys
POST /api/admin/tenants/{tenant_id}/api-keys/{api_key_id}/revoke
POST /api/admin/tenants/{tenant_id}/callback-credentials
GET  /api/admin/tenants/{tenant_id}/callback-credentials
POST /api/admin/tenants/{tenant_id}/callback-credentials/{credential_id}/revoke
GET  /api/tenant/context
POST /api/admin/persons
GET  /api/admin/persons
GET  /api/admin/persons/{person_id}
PATCH /api/admin/persons/{person_id}
POST /api/admin/departments
GET  /api/admin/departments
GET  /api/admin/departments/{department_id}
PATCH /api/admin/departments/{department_id}
POST /api/admin/departments/{department_id}/members
GET  /api/admin/departments/{department_id}/members
POST /api/admin/departments/{department_id}/members/{person_id}/disable
POST /api/admin/tenants/{tenant_id}/persons/bind
GET  /api/admin/tenants/{tenant_id}/persons
PATCH /api/admin/tenants/{tenant_id}/persons/{person_id}/binding
POST /api/admin/node-definitions
GET  /api/admin/node-definitions
GET  /api/admin/node-definitions/{node_definition_id}
PATCH /api/admin/node-definitions/{node_definition_id}
POST /api/admin/processes
GET  /api/admin/processes
GET  /api/admin/processes/{process_id}
GET  /api/admin/processes/{process_id}/versions
POST /api/admin/processes/{process_id}/draft
POST /api/admin/processes/{process_id}/copy
POST /api/admin/processes/{process_id}/disable
GET  /api/admin/process-versions/{version_id}/graph
PUT  /api/admin/process-versions/{version_id}/graph
POST /api/admin/process-versions/{version_id}/validate
POST /api/admin/process-versions/{version_id}/publish
POST /api/processes/{process_id}/instances
GET  /api/approval-instances/{instance_id}
GET  /api/approval-instances/{instance_id}/timeline
GET  /api/approval-tasks
POST /api/approval-tasks/{task_id}/approve
POST /api/approval-tasks/{task_id}/reject
POST /api/admin/business-actions
GET  /api/admin/business-actions
GET  /api/admin/business-actions/{action_id}
PATCH /api/admin/business-actions/{action_id}
POST /api/admin/tenants/{tenant_id}/process-bindings
GET  /api/admin/tenants/{tenant_id}/process-bindings
PATCH /api/admin/tenants/{tenant_id}/process-bindings/{binding_id}
POST /api/admin/tenants/{tenant_id}/business-action-bindings
GET  /api/admin/tenants/{tenant_id}/business-action-bindings
PATCH /api/admin/tenants/{tenant_id}/business-action-bindings/{binding_id}
GET  /api/admin/tenants/{tenant_id}/process-usage-records
GET  /api/admin/tenants/{tenant_id}/process-usage-records/{record_id}
GET  /api/admin/execution-records
GET  /api/admin/execution-records/{record_id}
```

`/api/admin/*` 使用 `X-Admin-Key`；`/api/tenant/context` 和发起审批使用租户的 `X-API-Key`。后续业务 API 可通过 `use_tenant_scope(resource_type)` 自动完成 API Key 认证和租户资源过滤；关闭 `TENANCY_ENABLED` 后，同一依赖会返回全局作用域。

### 业务系统发起审批

业务系统使用租户 API Key 调用发起接口，`tenant_id` 不由请求体传入：

```text
POST /api/processes/{process_id}/instances
X-API-Key: appr_live_xxx
```

```json
{
  "business_key": "PAY-20260921-001",
  "title": "供应商付款申请",
  "applicant_person_id": "人员UUID",
  "action_code": "PAYMENT_EXECUTE",
  "approval_form": { "amount": 10000 },
  "execution_payload": { "payment_id": "PAY-20260921-001", "amount": 10000 }
}
```

启用租户能力时，请求会依次校验 API Key、租户状态、流程授权、业务动作授权和执行参数，
并在同一个事务中提交审批实例、首批任务和租户使用记录。`action_code` 为空表示只完成审批
不触发业务执行。`TENANCY_ENABLED=false` 时不要求 API Key，也不写入租户使用记录，并且
**不接受 `action_code`**：全局模式没有租户归属，审批通过后没有可用的回调地址和 Service
Token，这类申请会在发起阶段直接返回 409。

完整接口清单、错误码和联调步骤见
`app/server/integration/docs/业务接入接口说明.md`。

审批运行接口暂未接入认证：接入项目平台登录身份前，任务查询和审批请求显式传递 `person_id`，发起审批在请求体中传递 `applicant_person_id`。

### 审批通过后的业务执行

审批最终通过时，`ApprovalEngine.finish_instance()` 在审批事务内创建唯一一条
`process.business_execution_record`（`PENDING`）并固化业务动作配置快照，事务中不发送任何
外部请求。事务提交后由后台 Worker 领取任务、调用业务系统并保存结果：

```text
PENDING → RUNNING → SUCCEEDED
                  → FAILED
```

执行器通过 `approval_instance_id` 和 `tenant.process_usage_record` 确定租户，再用
`tenant.callback_base_url` 加上动作相对路径组成请求地址，认证使用租户配置的 Service Token。
第一版不自动重试，也不根据执行结果修改审批状态；发送请求后进程异常退出可能留下 `RUNNING`
记录，由后台页面展示并交给人工核对。查询接口不返回 Service Token、密文和完整认证请求头。

`server/integration` 和 `server/process` 的第一版已经落地：业务动作定义与参数规则在
`integration`，审批流定义、运行和审批通过后的业务执行在 `process`。当前先保持单体
部署，按模块边界逐步实现。
