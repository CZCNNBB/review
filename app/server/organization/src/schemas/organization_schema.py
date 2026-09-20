"""人员与组织模块的请求与响应模型。"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def normalize_optional_text(value: str | None) -> str | None:
    """清理可选文本，空字符串统一保存为 None。"""

    if value is None:
        return None
    normalized_value = value.strip()
    return normalized_value or None


class PersonCreateRequest(BaseModel):
    """创建全局人员请求。"""

    name: str = Field(min_length=1, max_length=100)
    mobile: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """清理并校验人员姓名。"""

        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("人员姓名不能为空")
        return normalized_value

    @field_validator("mobile", "email")
    @classmethod
    def normalize_contact(cls, value: str | None) -> str | None:
        """清理联系方式并统一邮箱大小写。"""

        normalized_value = normalize_optional_text(value)
        if normalized_value and "@" in normalized_value:
            return normalized_value.lower()
        return normalized_value


class PersonUpdateRequest(BaseModel):
    """更新全局人员请求。"""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    mobile: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, pattern=r"^(ENABLED|DISABLED)$")

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
    mobile: str | None
    email: str | None
    status: str
    created_at: datetime
    updated_at: datetime

class DepartmentCreateRequest(BaseModel):
    """创建全局部门请求。"""

    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    name: str = Field(min_length=1, max_length=100)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        """统一部门编码格式。"""

        return value.upper()

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """清理并校验部门名称。"""

        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("部门名称不能为空")
        return normalized_value


class DepartmentUpdateRequest(BaseModel):
    """更新全局部门请求。"""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    status: str | None = Field(default=None, pattern=r"^(ENABLED|DISABLED)$")

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
    """全局部门响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    status: str
    created_at: datetime
    updated_at: datetime


class DepartmentMemberCreateRequest(BaseModel):
    """把全局人员加入部门的请求。"""

    person_id: UUID


class DepartmentMemberResponse(BaseModel):
    """人员部门关系响应。"""

    id: UUID
    department_id: UUID
    department_name: str
    person_id: UUID
    person_name: str
    status: str
    created_at: datetime
    updated_at: datetime


class PersonBindingRequest(BaseModel):
    """将人员绑定到租户时使用的租户内资料。"""

    person_id: UUID
    department_id: UUID | None = None
    employee_no: str | None = Field(default=None, max_length=64)
    external_user_id: str | None = Field(default=None, max_length=128)
    display_name: str | None = Field(default=None, max_length=100)

    @field_validator("employee_no", "external_user_id", "display_name")
    @classmethod
    def normalize_optional_fields(cls, value: str | None) -> str | None:
        """清理租户人员绑定的可选字段。"""

        return normalize_optional_text(value)


class PersonBindingUpdateRequest(BaseModel):
    """更新租户人员绑定请求。"""

    department_id: UUID | None = None
    employee_no: str | None = Field(default=None, max_length=64)
    external_user_id: str | None = Field(default=None, max_length=128)
    display_name: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, pattern=r"^(ENABLED|DISABLED)$")

    @model_validator(mode="after")
    def ensure_non_empty_update(self) -> "PersonBindingUpdateRequest":
        """确保更新请求至少显式提供一个字段。"""

        if not self.model_fields_set:
            raise ValueError("至少需要提供一个更新字段")
        return self

    @field_validator("employee_no", "external_user_id", "display_name")
    @classmethod
    def normalize_optional_fields(cls, value: str | None) -> str | None:
        """清理租户人员绑定的可选字段。"""

        return normalize_optional_text(value)


class PersonBindingResponse(BaseModel):
    """租户人员绑定及全局人员展示信息。"""

    binding_id: UUID
    tenant_id: UUID
    person_id: UUID
    person_name: str
    department_id: UUID | None
    department_name: str | None
    employee_no: str | None
    external_user_id: str | None
    display_name: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class DepartmentBindingRequest(BaseModel):
    """将全局部门绑定到租户的请求。"""

    department_id: UUID
    local_code: str | None = Field(default=None, max_length=64)

    @field_validator("local_code")
    @classmethod
    def normalize_local_code(cls, value: str | None) -> str | None:
        """清理并统一租户内部门编码。"""

        normalized_value = normalize_optional_text(value)
        return normalized_value.upper() if normalized_value else None


class DepartmentBindingResponse(BaseModel):
    """租户部门绑定及全局部门展示信息。"""

    binding_id: UUID
    tenant_id: UUID
    department_id: UUID
    department_code: str
    department_name: str
    local_code: str | None
    status: str
    created_at: datetime
    updated_at: datetime
