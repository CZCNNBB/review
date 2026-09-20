"""租户模块的 FastAPI 认证依赖。"""

from dataclasses import dataclass
from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from fastapi.params import Depends as DependsParameter
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.common.scope import ResourceScope
from app.common.security import verify_admin_key
from app.server.tenant.src.scope.tenant_scope import create_resource_scope, is_tenancy_enabled
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


def build_resource_scope_dependency(
    resource_type: str,
) -> Callable[..., ResourceScope]:
    """构造指定资源类型的 FastAPI 租户作用域依赖函数。"""

    def get_resource_scope(
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
        db: Session = Depends(get_postgres_engine),
    ) -> ResourceScope:
        """根据租户开关和 API Key 生成当前请求的资源作用域。"""

        # 关闭租户能力后，不再要求调用方提供 API Key，也不会查询租户绑定表。
        if not is_tenancy_enabled():
            return create_resource_scope(resource_type=resource_type)

        # 启用租户能力时复用统一认证逻辑，确保 tenant_id 只能来自可信 API Key。
        tenant_context = get_tenant_context(x_api_key=x_api_key, db=db)
        return create_resource_scope(
            resource_type=resource_type,
            tenant_id=tenant_context.tenant_id,
        )

    return get_resource_scope


def use_tenant_scope(resource_type: str) -> DependsParameter:
    """返回可直接声明在业务 API 参数上的租户作用域依赖。"""

    return Depends(build_resource_scope_dependency(resource_type))


__all__ = [
    "TenantAuthContext",
    "build_resource_scope_dependency",
    "get_tenant_context",
    "use_tenant_scope",
    "verify_admin_key",
]
