"""租户模块领域异常。"""


class TenantServiceError(Exception):
    """租户模块业务异常基类。"""


class TenantNotFoundError(TenantServiceError):
    """租户不存在。"""


class TenantConflictError(TenantServiceError):
    """租户或凭据发生唯一性冲突。"""


class CredentialNotFoundError(TenantServiceError):
    """指定凭据不存在。"""


class InvalidApiKeyError(TenantServiceError):
    """API Key 无效、失效或不允许访问。"""


class CredentialConfigurationError(TenantServiceError):
    """回调凭据加密配置不可用。"""
