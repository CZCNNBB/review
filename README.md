# 审批中心 Backend

这是审批中心使用的 FastAPI 后端脚手架。当前采用“微服务预备架构”：所有服务先放在一个 FastAPI 项目中运行，但每个服务模块都拥有独立的 `api` 接口层和 `src` 业务逻辑层，后续可以按需拆成真正的独立微服务。

数据库采用“每个 server 一个 PostgreSQL Schema”的约定。当前租户服务使用 `tenant` Schema。

## 设计文档

- `docs/审批中心整体设计.md`：系统边界、模块划分、核心链路和实施顺序。
- `docs/租户模块设计.md`：已经完成的租户模块设计。
- `docs/人员与组织模块设计.md`：下一阶段人员、租户成员和部门设计。

## 项目结构

```text
backend/
  app/
    main.py                       # FastAPI 应用创建与路由注册
    bootstrap.py                  # 启动初始化

    common/                       # 跨服务公共能力
      config/                     # 全局配置
      db/                         # 数据库连接
      schemas/                    # 通用响应、公共模型
      utils/                      # 公共工具函数

    server/                       # 后端服务模块集合
      tenant/
        api/                      # 租户管理与 API Key 认证接口
        src/
          models/                 # 租户、API Key、回调凭据模型
          schemas/                # 请求响应模型
          repository/             # 数据访问层
          service/                # 租户与凭据业务逻辑
          utils/                  # API Key 生成和回调凭据加密工具
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
```

租户管理接口使用临时管理密钥，后续接入项目平台管理员身份后替换：

```text
APPROVAL_ADMIN_KEY=请使用高强度随机值
```

回调签名密钥需要使用应用主密钥加密保存。可以执行：

```powershell
python -B -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

将结果写入：

```text
APPROVAL_CREDENTIAL_MASTER_KEY=生成的Fernet密钥
```

不要将实际密钥提交到代码仓库。

### 初始化数据库表

确认 PostgreSQL 环境变量配置完成后执行：

```powershell
python -B -m app.common.db.init_db
```

该命令会先执行 `CREATE SCHEMA IF NOT EXISTS tenant`，然后在其中创建租户模块数据表。它适用于开发期首次初始化；正式环境结构变更应切换到数据库迁移工具。

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
POST /api/admin/tenants/{tenant_id}/departments
GET  /api/admin/tenants/{tenant_id}/departments
PATCH /api/admin/tenants/{tenant_id}/departments/{department_id}
POST /api/admin/tenants/{tenant_id}/members
GET  /api/admin/tenants/{tenant_id}/members
GET  /api/admin/tenants/{tenant_id}/members/resolve
GET  /api/admin/tenants/{tenant_id}/members/{member_id}
PATCH /api/admin/tenants/{tenant_id}/members/{member_id}
```

`/api/admin/*` 使用 `X-Admin-Key`；`/api/tenant/context` 使用租户的 `X-API-Key`。

## 后续模块规划

```text
server/person     审批人员与租户成员
server/process    审批流配置
server/approval   审批实例、任务与操作记录
server/callback   业务动作回调与执行记录
```

当前先保持单体部署，按模块边界逐步实现。
