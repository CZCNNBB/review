"""租户模块的 FastAPI 认证依赖。"""

import hmac
import os
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.server.tenant.src.service.exceptions import InvalidApiKeyError
from app.server.tenant.src.service.tenant_service import TenantService


tenant_service = TenantService()


@dataclass(frozen=True)
class TenantAuthContext:
    """通过 API Key 验证后得到的可信租户上下文。"""

    tenant_id: UUID
    tenant_code: str
    tenant_name: str
    api_key_id: UUID


def verify_admin_key(x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")) -> None:
    """校验临时管理密钥，后续可替换为项目平台管理员身份。"""

    expected_admin_key = os.getenv("APPROVAL_ADMIN_KEY")
    if not expected_admin_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="未配置 APPROVAL_ADMIN_KEY，租户管理接口不可用",
        )
    if not x_admin_key or not hmac.compare_digest(x_admin_key, expected_admin_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="管理密钥无效")


def get_tenant_context(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_postgres_engine),
) -> TenantAuthContext:
    """验证业务系统 API Key 并构造当前租户上下文。"""

    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少 X-API-Key")
    try:
        tenant, api_key = tenant_service.authenticate_api_key(x_api_key, db)
    except InvalidApiKeyError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    return TenantAuthContext(
        tenant_id=tenant.id,
        tenant_code=tenant.code,
        tenant_name=tenant.name,
        api_key_id=api_key.id,
    )
