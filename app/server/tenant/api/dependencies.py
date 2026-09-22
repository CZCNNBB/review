"""租户模块的 FastAPI 认证依赖。"""

from dataclasses import dataclass
from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.params import Depends as DependsParameter
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.common.scope import ResourceScope
from app.common.security import verify_admin_key
from app.server.tenant.src.scope.business_access import (
    BusinessAccessContext,
    create_business_access_context,
)
from app.server.tenant.src.scope.tenant_scope import (
    TenantResourceAccessError,
    create_resource_scope,
    is_tenancy_enabled,
)
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


def get_business_access_context(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_postgres_engine),
) -> BusinessAccessContext:
    """构造业务接入接口使用的租户上下文。

    一个请求只在这里认证一次 API Key，流程、业务动作和使用记录三类作用域共用同一次
    认证结果，避免重复校验 API Key 和重复更新最近使用时间。关闭租户能力时既不要求
    API Key，也不会查询任何 tenant 表。
    """

    if not is_tenancy_enabled():
        return create_business_access_context(tenant_id=None)

    tenant_context = get_tenant_context(x_api_key=x_api_key, db=db)
    return create_business_access_context(tenant_id=tenant_context.tenant_id)


def use_business_access_context() -> DependsParameter:
    """返回可直接声明在业务接入 API 参数上的上下文依赖。"""

    return Depends(get_business_access_context)


def build_tenant_access_dependency(
    resource_type: str,
    resource_id_param: str,
) -> Callable[..., None]:
    """构造从路径参数读取资源 ID 并校验租户访问权的依赖函数。"""

    resource_scope_dependency = build_resource_scope_dependency(resource_type)

    def check_tenant_access(
        request: Request,
        scope: ResourceScope = Depends(resource_scope_dependency),
        db: Session = Depends(get_postgres_engine),
    ) -> None:
        """在业务接口执行前完成租户资源访问校验。"""

        raw_resource_id = request.path_params.get(resource_id_param)
        if raw_resource_id is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"路由缺少资源参数：{resource_id_param}",
            )

        try:
            resource_id = UUID(str(raw_resource_id))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"资源参数 {resource_id_param} 不是有效的 UUID",
            ) from exc

        try:
            scope.require_access(resource_id, db)
        except TenantResourceAccessError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc

    return check_tenant_access


def require_tenant_access(
    resource_type: str,
    resource_id_param: str,
) -> DependsParameter:
    """返回可直接放入路由 dependencies 列表的租户访问守卫。"""

    dependency = build_tenant_access_dependency(
        resource_type=resource_type,
        resource_id_param=resource_id_param,
    )
    return Depends(dependency)


__all__ = [
    "BusinessAccessContext",
    "TenantAuthContext",
    "build_tenant_access_dependency",
    "build_resource_scope_dependency",
    "get_business_access_context",
    "get_tenant_context",
    "require_tenant_access",
    "use_business_access_context",
    "use_tenant_scope",
    "verify_admin_key",
]
