import app.bootstrap  # 初始化异步环境, 必须最先导入
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.server.user.api import router as user_router
from app.server.spider.api import router as spider_router
import uvicorn


def create_app() -> FastAPI:
    """
    创建FastAPI实例
    """
    app = FastAPI()
    
    # 配置 CORS 中间件，允许所有来源访问
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 注册各微服务模块的接口层。每个服务只通过自己的 api 聚合出口对外暴露接口。
    app.include_router(user_router, prefix="/user", tags=["user模块"])
    app.include_router(spider_router, prefix="/spider", tags=["spider模块"])
    
    @app.get("/")
    def root_endpoint():
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
        host=os.getenv("FastApi_host","127.0.0.1"),   
        port=int(os.getenv("FastApi_port",8090)),
        loop="asyncio",     # 使用 asyncio 事件循环
        workers=1,          # 启动的进程个数
        reload=True,        # 自动重载代码变更，异步下需要设置为 True
        factory=True        # 启用 factory 模式，该模式下必须指定 "模块名:函数名"，作用是每个进程独立创建 FastAPI 实例
    )
    
