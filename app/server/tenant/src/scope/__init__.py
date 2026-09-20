"""租户资源作用域导出。"""

from app.server.tenant.src.scope.tenant_scope import (
    RESOURCE_PERSON,
    TenantResourceScope,
    create_resource_scope,
    is_tenancy_enabled,
)

__all__ = [
    "RESOURCE_PERSON",
    "TenantResourceScope",
    "create_resource_scope",
    "is_tenancy_enabled",
]
