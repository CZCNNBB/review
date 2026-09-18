# 就业指导 AI 平台 Backend

这是就业指导 AI 平台的后端项目。当前采用“微服务预备架构”：所有服务先放在一个 FastAPI 项目中运行，但每个服务模块都拥有独立的 `api` 接口层和 `src` 业务逻辑层，后续可以按需拆成真正的独立微服务。

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
cd D:\study\get_job_data\backend
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

## 当前接口

```text
GET  /
POST /user/login
POST /user/register
GET  /spider/health
```

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
