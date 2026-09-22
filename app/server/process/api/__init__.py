"""审批流定义与运行模块 API 聚合出口。"""

from fastapi import APIRouter

from app.server.process.api.approval_instance_api import (
    router as approval_instance_router,
)
from app.server.process.api.approval_task_api import router as approval_task_router
from app.server.process.api.execution_record_api import (
    router as execution_record_router,
)
from app.server.process.api.node_definition_api import router as node_definition_router
from app.server.process.api.process_api import router as process_router

router = APIRouter()
router.include_router(node_definition_router)
router.include_router(process_router)
router.include_router(approval_instance_router)
router.include_router(approval_task_router)
router.include_router(execution_record_router)

__all__ = ["router"]
