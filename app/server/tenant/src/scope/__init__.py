"""租户资源作用域导出。"""

from app.server.tenant.src.scope.tenant_scope import (
    RESOURCE_APPROVAL_INSTANCE,
    RESOURCE_BUSINESS_ACTION,
    RESOURCE_PERSON,
    RESOURCE_PROCESS,
    TenantResourceAccessError,
    TenantResourceScope,
    create_resource_scope,
    is_tenancy_enabled,
)

__all__ = [
    "RESOURCE_APPROVAL_INSTANCE",
    "RESOURCE_BUSINESS_ACTION",
    "RESOURCE_PERSON",
    "RESOURCE_PROCESS",
    "TenantResourceAccessError",
    "TenantResourceScope",
    "create_resource_scope",
    "is_tenancy_enabled",
]
