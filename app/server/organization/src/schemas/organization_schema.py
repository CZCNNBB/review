"""人员与组织模块的请求与响应模型。"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def normalize_optional_text(value: str | None) -> str | None:
    """清理可选文本，空字符串统一保存为 None。"""

    if value is None:
        return None

    normalized_value = value.strip()
    if not normalized_value:
        return None
    return normalized_value


class PersonCreateRequest(BaseModel):
    """创建全局人员请求。"""

    name: str = Field(min_length=1, max_length=100)
    mobile: Optional[str] = Field(default=None, max_length=32)
    email: Optional[str] = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """清理人员姓名两侧空白。"""

        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("人员姓名不能为空")
        return normalized_value

    @field_validator("mobile", "email")
    @classmethod
    def normalize_contact(cls, value: str | None) -> str | None:
        """清理手机号和邮箱，空字符串转换为 None。"""

        normalized_value = normalize_optional_text(value)
        if normalized_value and "@" in normalized_value:
            return normalized_value.lower()
        return normalized_value


class PersonUpdateRequest(BaseModel):
    """更新全局人员请求。"""

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    mobile: Optional[str] = Field(default=None, max_length=32)
    email: Optional[str] = Field(default=None, max_length=255)
    status: Optional[str] = Field(default=None, pattern=r"^(ENABLED|DISABLED)$")

    @model_validator(mode="after")
    def ensure_non_empty_update(self) -> "PersonUpdateRequest":
        """确保更新请求至少显式提供一个字段。"""

        if not self.model_fields_set:
            raise ValueError("至少需要提供一个更新字段")
        return self

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        """清理可选人员姓名。"""

        if value is None:
            raise ValueError("人员姓名不能设置为空")
        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("人员姓名不能为空")
        return normalized_value

    @field_validator("mobile", "email")
    @classmethod
    def normalize_contact(cls, value: str | None) -> str | None:
        """清理可选联系方式。"""

        normalized_value = normalize_optional_text(value)
        if normalized_value and "@" in normalized_value:
            return normalized_value.lower()
        return normalized_value


class PersonResponse(BaseModel):
    """全局人员响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    mobile: Optional[str]
    email: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime


class DepartmentCreateRequest(BaseModel):
    """创建租户部门请求。"""

    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    name: str = Field(min_length=1, max_length=100)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        """将部门编码统一转换为大写。"""

        return value.upper()

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """清理部门名称两侧空白。"""

        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("部门名称不能为空")
        return normalized_value


class DepartmentUpdateRequest(BaseModel):
    """更新租户部门请求。"""

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    status: Optional[str] = Field(default=None, pattern=r"^(ENABLED|DISABLED)$")

    @model_validator(mode="after")
    def ensure_non_empty_update(self) -> "DepartmentUpdateRequest":
        """确保更新请求至少显式提供一个字段。"""

        if not self.model_fields_set:
            raise ValueError("至少需要提供一个更新字段")
        return self

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        """清理可选部门名称。"""

        if value is None:
            raise ValueError("部门名称不能设置为空")
        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("部门名称不能为空")
        return normalized_value


class DepartmentResponse(BaseModel):
    """租户部门响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    code: str
    name: str
    status: str
    created_at: datetime
    updated_at: datetime


class TenantMemberCreateRequest(BaseModel):
    """创建租户成员请求。"""

    person_id: UUID
    department_id: Optional[UUID] = None
    employee_no: Optional[str] = Field(default=None, max_length=64)
    external_user_id: Optional[str] = Field(default=None, max_length=128)
    display_name: Optional[str] = Field(default=None, max_length=100)

    @field_validator("employee_no", "external_user_id", "display_name")
    @classmethod
    def normalize_optional_fields(cls, value: str | None) -> str | None:
        """清理租户成员可选文本字段。"""

        return normalize_optional_text(value)


class TenantMemberUpdateRequest(BaseModel):
    """更新租户成员请求。"""

    department_id: Optional[UUID] = None
    employee_no: Optional[str] = Field(default=None, max_length=64)
    external_user_id: Optional[str] = Field(default=None, max_length=128)
    display_name: Optional[str] = Field(default=None, max_length=100)
    status: Optional[str] = Field(default=None, pattern=r"^(ENABLED|DISABLED)$")

    @model_validator(mode="after")
    def ensure_non_empty_update(self) -> "TenantMemberUpdateRequest":
        """确保更新请求至少显式提供一个字段。"""

        if not self.model_fields_set:
            raise ValueError("至少需要提供一个更新字段")
        return self

    @field_validator("employee_no", "external_user_id", "display_name")
    @classmethod
    def normalize_optional_fields(cls, value: str | None) -> str | None:
        """清理租户成员可选文本字段。"""

        return normalize_optional_text(value)


class TenantMemberResponse(BaseModel):
    """租户成员响应，包含管理页面需要的人员和部门名称。"""

    id: UUID
    tenant_id: UUID
    person_id: UUID
    person_name: str
    department_id: Optional[UUID]
    department_name: Optional[str]
    employee_no: Optional[str]
    external_user_id: Optional[str]
    display_name: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
