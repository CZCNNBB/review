"""租户模块的 Pydantic 请求与响应模型。"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator


class TenantCreateRequest(BaseModel):
    """创建租户请求。"""

    code: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    name: str = Field(min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=500)
    callback_base_url: AnyHttpUrl

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        """将租户编码统一转换为大写格式。"""

        return value.upper()

    @field_validator("callback_base_url")
    @classmethod
    def validate_callback_base_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        """回调基础地址不能包含查询参数或片段。"""

        if value.query or value.fragment:
            raise ValueError("回调基础地址不能包含查询参数或片段")
        return value


class TenantUpdateRequest(BaseModel):
    """更新租户请求。"""

    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=500)
    callback_base_url: Optional[AnyHttpUrl] = None
    status: Optional[str] = Field(default=None, pattern=r"^(ENABLED|DISABLED)$")

    @model_validator(mode="after")
    def ensure_non_empty_update(self) -> "TenantUpdateRequest":
        """确保更新请求至少包含一个字段。"""

        if not self.model_fields_set:
            raise ValueError("至少需要提供一个更新字段")
        return self

    @field_validator("callback_base_url")
    @classmethod
    def validate_callback_base_url(cls, value: AnyHttpUrl | None) -> AnyHttpUrl | None:
        """更新后的回调基础地址不能包含查询参数或片段。"""

        if value and (value.query or value.fragment):
            raise ValueError("回调基础地址不能包含查询参数或片段")
        return value


def validate_future_datetime(value: datetime | None) -> datetime | None:
    """校验可选过期时间必须晚于当前时间。"""

    if value is None:
        return None
    normalized_value = value
    if normalized_value.tzinfo is None:
        normalized_value = normalized_value.replace(tzinfo=timezone.utc)
    if normalized_value <= datetime.now(timezone.utc):
        raise ValueError("过期时间必须晚于当前时间")
    return value


class TenantResponse(BaseModel):
    """租户响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: Optional[str]
    callback_base_url: str
    status: str
    created_at: datetime
    updated_at: datetime


class ApiKeyCreateRequest(BaseModel):
    """创建 API Key 请求。"""

    name: str = Field(min_length=1, max_length=100)
    expires_at: Optional[datetime] = None

    @field_validator("expires_at")
    @classmethod
    def validate_expiration(cls, value: datetime | None) -> datetime | None:
        """校验 API Key 过期时间。"""

        return validate_future_datetime(value)


class ApiKeyResponse(BaseModel):
    """API Key 响应，包含管理页面可查看的完整明文。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    api_key: str
    status: str
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    created_at: datetime
    revoked_at: Optional[datetime]


class ApiKeyCreatedResponse(ApiKeyResponse):
    """API Key 创建响应，与详情响应保持相同字段。"""


class CallbackCredentialCreateRequest(BaseModel):
    """创建回调签名凭据请求。"""

    name: str = Field(min_length=1, max_length=100)
    expires_at: Optional[datetime] = None

    @field_validator("expires_at")
    @classmethod
    def validate_expiration(cls, value: datetime | None) -> datetime | None:
        """校验回调凭据过期时间。"""

        return validate_future_datetime(value)


class CallbackCredentialResponse(BaseModel):
    """回调签名凭据元数据响应，不包含密钥明文和密文。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    key_id: str
    status: str
    expires_at: Optional[datetime]
    created_at: datetime
    revoked_at: Optional[datetime]


class CallbackCredentialCreatedResponse(CallbackCredentialResponse):
    """回调签名凭据创建响应，secret 只在本次响应中展示。"""

    secret: str


class TenantContextResponse(BaseModel):
    """当前 API Key 对应的租户上下文。"""

    tenant_id: UUID
    tenant_code: str
    tenant_name: str
    api_key_id: UUID
