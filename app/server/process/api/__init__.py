"""审批流定义模块 API 聚合出口。"""

from fastapi import APIRouter

from app.server.process.api.node_definition_api import router as node_definition_router
from app.server.process.api.process_api import router as process_router


router = APIRouter()
router.include_router(node_definition_router)
router.include_router(process_router)

__all__ = ["router"]
