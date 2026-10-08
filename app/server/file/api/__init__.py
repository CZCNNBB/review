"""文件模块公开路由聚合出口。"""

from fastapi import APIRouter

from app.server.file.api.file_api import router as file_router


router = APIRouter()
router.include_router(file_router)

__all__ = ["router"]
