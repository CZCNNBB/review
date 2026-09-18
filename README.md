# 审批中心 Backend

这是审批中心使用的 FastAPI 后端脚手架。当前采用“微服务预备架构”：所有服务先放在一个 FastAPI 项目中运行，但每个服务模块都拥有独立的 `api` 接口层和 `src` 业务逻辑层，后续可以按需拆成真正的独立微服务。

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
      user/
        api/
          __init__.py             # 用户服务 API 聚合出口
          user_api.py             # 用户服务接口层
        src/
          config/                 # 用户服务内部配置
          schemas/                # 用户请求/响应模型
          models/                 # 用户服务数据库模型
          repository/             # 用户服务数据访问层
          service/                # 用户服务业务逻辑层
          utils/                  # 用户服务工具函数

      tenant/
        api/                      # 租户管理与 API Key 认证接口
        src/
          models/                 # 租户、API Key、回调凭据模型
          schemas/                # 请求响应模型
          repository/             # 数据访问层
          service/                # 租户与凭据业务逻辑
          utils/                  # 密钥生成、哈希和加密工具

      spider/
        api/
          __init__.py             # 爬虫服务 API 聚合出口
          spider_api.py           # 爬虫服务接口层
        src/
          QCWY/                   # 前程无忧采集器
          BOSSZP/                 # BOSS 直聘采集资料
          LP/                     # 猎聘采集资料
```

## 分层约定

每个服务模块遵循同一套边界：

```text
api/     对外 API 接口层，只处理请求参数、响应包装、依赖注入
src/     服务内部业务逻辑、采集器、数据库操作、模型和工具
common/  多个服务都会用到的公共能力
```

例如用户服务：

```text
app/server/user/api/user_api.py
app/server/user/src/config/user_config.py
app/server/user/src/schemas/request.py
app/server/user/src/schemas/response.py
app/server/user/src/models/user_model.py
app/server/user/src/repository/user_repository.py
app/server/user/src/service/user_service.py
app/server/user/src/utils/password.py
```

例如爬虫服务：

```text
app/server/spider/api/spider_api.py
app/server/spider/src/QCWY
```

## 启动方式

安装依赖：

```powershell
cd D:\work\DaiJun\ZhiHuiBan\ShenPi\backend
pip install -r requirements.txt
```

如果要使用 Playwright 自带 Chromium 浏览器执行爬虫，可以继续安装浏览器：

```powershell
playwright install chromium
```

如果已经在爬虫配置中指定本机 Chrome/Edge 路径，可以跳过这一步。

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

该命令适用于开发期首次初始化。正式环境结构变更应切换到数据库迁移工具。

## 当前接口

```text
GET  /
POST /user/login
POST /user/register
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
```

`/api/admin/*` 使用 `X-Admin-Key`；`/api/tenant/context` 使用租户的 `X-API-Key`。

## 后续模块规划

```text
server/user       用户登录注册
server/spider     招聘数据采集
server/job        岗位库与岗位查询
server/agent      LangGraph 分析流程
server/resume     简历解析
server/learning   学习计划与成长闭环
```

当前先保持单体部署。等 `spider`、`agent` 等模块复杂后，再把对应目录单独拆成进程或仓库。
