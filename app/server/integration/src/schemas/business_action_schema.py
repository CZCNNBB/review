"""业务动作的请求与响应模型。"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.server.integration.src.constants import (
    ACTION_CODE_PATTERN,
    ACTION_STATUS_PATTERN,
    MAX_TIMEOUT_MS,
    MIN_TIMEOUT_MS,
    SUPPORTED_HTTP_METHODS,
)
from app.server.process.src.schemas.process_schema import (
    normalize_optional_text,
    normalize_required_text,
)


def validate_relative_path(value: str) -> str:
    """校验回调相对路径只表达租户站点内的路径。

    最终调用地址只能由租户的 callback_base_url 和本字段拼接得到，因此这里必须拒绝
    完整 URL 和协议相对地址，避免业务发起请求绕过租户预先登记的回调地址。
    """

    normalized_value = value.strip()
    if not normalized_value.startswith("/"):
        raise ValueError("相对路径必须以 / 开头")
    if normalized_value.startswith("//"):
        raise ValueError("相对路径不能以 // 开头")
    if "://" in normalized_value:
        raise ValueError("相对路径不能是完整 URL")
    return normalized_value


def validate_success_status_codes(value: list[int] | None) -> Optional[list[int]]:
    """校验成功状态码数组，去重并升序保存。"""

    if value is None:
        return None
    if not value:
        # 空数组表示全部 2xx 视为成功。
        return []
    for status_code in value:
        if status_code < 100 or status_code > 599:
            raise ValueError(f"状态码 {status_code} 不是合法的 HTTP 状态码")
    return sorted(set(value))


class BusinessActionCreateRequest(BaseModel):
    """创建业务动作请求。"""

    action_code: str = Field(min_length=1, max_length=100, pattern=ACTION_CODE_PATTERN)
    name: str = Field(min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=500)
    http_method: str = Field(default="POST")
    relative_path: str = Field(min_length=1, max_length=500)
    request_schema_json: dict[str, Any] = Field(default_factory=dict)
    success_status_codes: list[int] | None = None
    timeout_ms: int = Field(default=5000, ge=MIN_TIMEOUT_MS, le=MAX_TIMEOUT_MS)

    @field_validator("action_code")
    @classmethod
    def normalize_action_code(cls, value: str) -> str:
        """统一业务动作标识的大小写，避免出现只差大小写的重复动作。"""

        return normalize_required_text(value).upper()

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """清理业务动作展示名称。"""

        return normalize_required_text(value)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        """清理动作说明，纯空白视为没有填写。"""

        return normalize_optional_text(value)

    @field_validator("http_method")
    @classmethod
    def validate_http_method(cls, value: str) -> str:
        """第一版只允许 POST、PUT、PATCH 三种调用方法。"""

        normalized_value = value.strip().upper()
        if normalized_value not in SUPPORTED_HTTP_METHODS:
            supported_values = "、".join(SUPPORTED_HTTP_METHODS)
            raise ValueError(f"调用方法必须是 {supported_values} 之一")
        return normalized_value

    @field_validator("relative_path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        """校验回调相对路径。"""

        return validate_relative_path(value)

    @field_validator("success_status_codes")
    @classmethod
    def validate_status_codes(cls, value: list[int] | None) -> Optional[list[int]]:
        """校验成功状态码数组。"""

        return validate_success_status_codes(value)


class BusinessActionUpdateRequest(BaseModel):
    """更新业务动作请求。

    业务动作只允许修改展示信息、调用配置和状态，action_code 创建后保持稳定，
    已经保存过执行参数的审批实例不受影响。
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=500)
    http_method: Optional[str] = Field(default=None)
    relative_path: Optional[str] = Field(default=None, min_length=1, max_length=500)
    request_schema_json: Optional[dict[str, Any]] = None
    success_status_codes: Optional[list[int]] = None
    timeout_ms: Optional[int] = Field(
        default=None,
        ge=MIN_TIMEOUT_MS,
        le=MAX_TIMEOUT_MS,
    )
    status: Optional[str] = Field(default=None, pattern=ACTION_STATUS_PATTERN)

    @model_validator(mode="after")
    def ensure_non_empty_update(self) -> "BusinessActionUpdateRequest":
        """确保更新请求至少包含一个字段。"""

        if not self.model_fields_set:
            raise ValueError("至少需要提供一个更新字段")
        return self

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        """清理业务动作展示名称。"""

        return normalize_required_text(value) if value is not None else None

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        """清理动作说明。"""

        return normalize_optional_text(value)

    @field_validator("http_method")
    @classmethod
    def validate_http_method(cls, value: str | None) -> str | None:
        """校验调用方法。"""

        if value is None:
            return None
        normalized_value = value.strip().upper()
        if normalized_value not in SUPPORTED_HTTP_METHODS:
            supported_values = "、".join(SUPPORTED_HTTP_METHODS)
            raise ValueError(f"调用方法必须是 {supported_values} 之一")
        return normalized_value

    @field_validator("relative_path")
    @classmethod
    def validate_path(cls, value: str | None) -> str | None:
        """校验回调相对路径。"""

        return validate_relative_path(value) if value is not None else None

    @field_validator("success_status_codes")
    @classmethod
    def validate_status_codes(cls, value: list[int] | None) -> Optional[list[int]]:
        """校验成功状态码数组。"""

        return validate_success_status_codes(value)


class BusinessActionResponse(BaseModel):
    """业务动作响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action_code: str
    name: str
    description: Optional[str]
    http_method: str
    relative_path: str
    request_schema: dict[str, Any]
    success_status_codes: list[int]
    timeout_ms: int
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_action(cls, action: Any) -> "BusinessActionResponse":
        """把数据库模型转换成响应，JSON 列按接口语义重新命名。"""

        return cls(
            id=action.id,
            action_code=action.action_code,
            name=action.name,
            description=action.description,
            http_method=action.http_method,
            relative_path=action.relative_path,
            request_schema=dict(action.request_schema_json or {}),
            success_status_codes=list(action.success_status_codes_json or []),
            timeout_ms=action.timeout_ms,
            status=action.status,
            created_at=action.created_at,
            updated_at=action.updated_at,
        )
