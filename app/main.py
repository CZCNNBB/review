import asyncio
import os
import sys
from pathlib import Path

# 支持在 backend/app 目录直接执行 `python main.py`。直接运行脚本时，Python
# 默认只把 app 目录加入模块搜索路径，需要主动补充它的父目录 backend。
if __package__ in {None, ""}:
    backend_directory = Path(__file__).resolve().parent.parent
    backend_directory_text = str(backend_directory)
    if backend_directory_text not in sys.path:
        sys.path.insert(0, backend_directory_text)

import app.bootstrap  # 初始化异步环境，必须在其他项目模块之前导入

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.server.integration.api import router as integration_router
from app.server.organization.api import router as organization_router
from app.server.process.api import router as process_router
from app.server.process.src.execution.bootstrap import (
    start_business_execution_worker,
    stop_business_execution_worker,
)
from app.server.tenant.api import router as tenant_router
import uvicorn


@asynccontextmanager
async def lifespan(_: FastAPI):
    """应用启动时启动业务执行 Worker，关闭时有序停止。

    Worker 在独立线程中轮询，不占用当前事件循环。多个 Uvicorn 进程各自启动一个
    Worker，重复领取由 PostgreSQL 的 FOR UPDATE SKIP LOCKED 兜住。
    """

    worker = start_business_execution_worker()
    try:
        yield
    finally:
        # 停机等待属于同步阻塞操作，放到工作线程中执行，避免阻塞 FastAPI 事件循环中的
        # 其他 lifespan 清理动作。Worker 会先停止领取，再等待当前 RUNNING 任务落库。
        await asyncio.to_thread(stop_business_execution_worker, worker)


def _mount_console(app: FastAPI) -> None:
    """把 Vue 版配置台的构建产物挂到 /console 下。

    前端路由用的是 hash 模式，所以 /console/ 这一个入口就能兜住全部页面，不需要
    服务端做 history fallback。产物没构建时（全新克隆的仓库）静默跳过，不能让
    后端因为少了一个前端目录就起不来。
    """

    dist_directory = Path(__file__).resolve().parent.parent / "web-vue" / "dist"
    if not dist_directory.is_dir():
        return

    app.mount(
        "/console",
        StaticFiles(directory=str(dist_directory), html=True),
        name="console",
    )


def create_app() -> FastAPI:
    """
    创建FastAPI实例
    """
    app = FastAPI(lifespan=lifespan)
    
    # 配置 CORS 中间件，允许所有来源访问
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 注册各微服务模块的接口层。每个服务只通过自己的 api 聚合出口对外暴露接口。
    app.include_router(tenant_router, prefix="/api", tags=["租户模块"])
    app.include_router(organization_router, prefix="/api", tags=["人员与组织模块"])
    app.include_router(process_router, prefix="/api", tags=["审批流维护模块"])
    app.include_router(integration_router, prefix="/api", tags=["业务接入模块"])

    _mount_console(app)

    @app.get("/")
    def root_endpoint():
        """返回审批中心后端的基础可用状态。"""

        return {"message": "统一入口"}

    return app


if __name__ == "__main__":

    app = create_app()
    
    # 打印所有路由
    print("当前 FastAPI 已注册路由列表：")
    for route in app.routes:
        if hasattr(route, 'path'):
            print(f"{route.path}")
        else:
            print(f"  {route} - {type(route)}")
   
    # 生产环境配置（多进程）
    uvicorn.run(
        "app.main:create_app",   # 用 factory 模式, 必须在 uvicorn.run 中指定 factory=True
        host=os.getenv("FASTAPI_HOST", "127.0.0.1"),
        port=int(os.getenv("FASTAPI_PORT", "8090")),
        loop="asyncio",     # 使用 asyncio 事件循环
        workers=1,          # 启动的进程个数
        reload=True,        # 自动重载代码变更，异步下需要设置为 True
        factory=True        # 启用 factory 模式，该模式下必须指定 "模块名:函数名"，作用是每个进程独立创建 FastAPI 实例
    )
    
