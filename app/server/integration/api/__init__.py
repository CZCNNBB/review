"""业务接入模块 API 聚合出口。"""

from fastapi import APIRouter

from app.server.integration.api.business_action_api import (
    raise_business_access_http_error,
)
from app.server.integration.api.business_action_api import router as business_action_router


router = APIRouter()
router.include_router(business_action_router)

__all__ = ["raise_business_access_http_error", "router"]
