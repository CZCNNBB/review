"""租户模块请求与响应模型。"""

from app.server.tenant.src.schemas.tenant_schema import (
    ApiKeyCreateRequest,
    ApiKeyCreatedResponse,
    ApiKeyResponse,
    CallbackCredentialCreateRequest,
    CallbackCredentialCreatedResponse,
    CallbackCredentialResponse,
    TenantContextResponse,
    TenantCreateRequest,
    TenantResponse,
    TenantUpdateRequest,
)

__all__ = [
    "ApiKeyCreateRequest",
    "ApiKeyCreatedResponse",
    "ApiKeyResponse",
    "CallbackCredentialCreateRequest",
    "CallbackCredentialCreatedResponse",
    "CallbackCredentialResponse",
    "TenantContextResponse",
    "TenantCreateRequest",
    "TenantResponse",
    "TenantUpdateRequest",
]
