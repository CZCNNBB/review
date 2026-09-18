"""租户模块 API 聚合出口。"""

from fastapi import APIRouter

from app.server.tenant.api.tenant_api import router as tenant_router


router = APIRouter()
router.include_router(tenant_router)
