"""节点能力定义的请求与响应模型。"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.server.process.src.constants import (
    NODE_DEFINITION_STATUS_PATTERN,
    NODE_TYPE_PATTERN,
)
from app.server.process.src.utils.json_schema import validate_object_schema


def normalize_optional_text(value: str | None) -> str | None:
    """清理可选文本，空字符串统一保存为 None。"""

    if value is None:
        return None
    normalized_value = value.strip()
    return normalized_value or None


class NodeDefinitionCreateRequest(BaseModel):
    """创建节点能力定义请求。"""

    node_type: str = Field(pattern=NODE_TYPE_PATTERN)
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    icon: str | None = Field(default=None, max_length=100)
    config_schema_json: dict[str, Any] = Field(default_factory=dict)
    ui_schema_json: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="ENABLED", pattern=NODE_DEFINITION_STATUS_PATTERN)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """清理并校验节点定义名称。"""

        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("节点定义名称不能为空")
        return normalized_value

    @field_validator("description", "icon")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        """清理可选文本字段。"""

        return normalize_optional_text(value)

    @field_validator("config_schema_json")
    @classmethod
    def validate_node_config_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        """校验节点配置 Schema 合法且根类型为对象。"""

        return validate_object_schema(value, label="节点配置")


class NodeDefinitionUpdateRequest(BaseModel):
    """更新节点能力定义请求。

    node_type 不在可更新字段内：把已经上线流程引用的 START 改成 APPROVAL 会让
    既有流程语义错乱，需要改成新增一条节点定义。
    """

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    icon: str | None = Field(default=None, max_length=100)
    config_schema_json: dict[str, Any] | None = None
    ui_schema_json: dict[str, Any] | None = None
    status: str | None = Field(default=None, pattern=NODE_DEFINITION_STATUS_PATTERN)

    @model_validator(mode="after")
    def ensure_non_empty_update(self) -> "NodeDefinitionUpdateRequest":
        """确保更新请求至少显式提供一个字段。"""

        if not self.model_fields_set:
            raise ValueError("至少需要提供一个更新字段")
        return self

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        """清理可选节点定义名称。"""

        if value is None:
            raise ValueError("节点定义名称不能设置为空")
        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("节点定义名称不能为空")
        return normalized_value

    @field_validator("description", "icon")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        """清理可选文本字段。"""

        return normalize_optional_text(value)

    @field_validator("config_schema_json")
    @classmethod
    def validate_node_config_schema(
        cls,
        value: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """校验节点配置 Schema 合法且根类型为对象。"""

        if value is None:
            return None
        return validate_object_schema(value, label="节点配置")


class NodeDefinitionResponse(BaseModel):
    """节点能力定义响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    node_type: str
    name: str
    description: str | None
    icon: str | None
    config_schema_json: dict[str, Any]
    ui_schema_json: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime
