"""审批流主体、版本、编排和校验结果的请求响应模型。"""

from datetime import datetime
from typing import Any, Sequence
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.server.process.src.utils.json_schema import validate_object_schema


def normalize_optional_text(value: str | None) -> str | None:
    """清理可选文本，空字符串统一保存为 None。"""

    if value is None:
        return None
    normalized_value = value.strip()
    return normalized_value or None


def normalize_required_text(value: str) -> str:
    """清理必填文本，纯空白视为非法。"""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError("内容不能为空")
    return normalized_value


class ProcessCreateRequest(BaseModel):
    """创建审批流及其 V1 草稿请求。"""

    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=500)
    form_schema: dict[str, Any] = Field(default_factory=dict)
    form_ui_schema: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """清理并校验流程名称。"""

        return normalize_required_text(value)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        """清理流程说明。"""

        return normalize_optional_text(value)

    @field_validator("form_schema")
    @classmethod
    def validate_form_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        """校验审批表单 Schema 合法且根类型为对象。"""

        return validate_object_schema(value, label="审批表单")


class ProcessGraphNodeRequest(BaseModel):
    """整图保存中的单个版本节点。"""

    id: UUID
    node_definition_id: UUID
    name: str = Field(min_length=1, max_length=128)
    config: dict[str, Any] = Field(default_factory=dict)
    position: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """清理并校验节点名称。"""

        return normalize_required_text(value)

    @field_validator("position")
    @classmethod
    def validate_position(cls, value: dict[str, Any]) -> dict[str, Any]:
        """校验画布坐标，存在时必须是非布尔数字。"""

        for axis_name in ("x", "y"):
            axis_value = value.get(axis_name)
            if axis_value is None:
                continue
            if isinstance(axis_value, bool) or not isinstance(axis_value, (int, float)):
                raise ValueError(f"节点画布坐标 {axis_name} 必须是数字")
        return value


class ProcessGraphSaveRequest(BaseModel):
    """草稿版本整图保存请求。"""

    revision: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=500)
    form_schema: dict[str, Any] | None = None
    form_ui_schema: dict[str, Any] | None = None
    nodes: list[ProcessGraphNodeRequest] = Field(default_factory=list)
    orchestration: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def ensure_unique_node_ids(self) -> "ProcessGraphSaveRequest":
        """确保同一次请求中的节点 ID 唯一。"""

        seen_node_ids: set[UUID] = set()
        for node in self.nodes:
            if node.id in seen_node_ids:
                raise ValueError(f"节点 ID 在请求内重复：{node.id}")
            seen_node_ids.add(node.id)
        return self

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """清理并校验版本名称。"""

        return normalize_required_text(value)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        """清理版本说明。"""

        return normalize_optional_text(value)

    @field_validator("form_schema")
    @classmethod
    def validate_form_schema(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        """校验审批表单 Schema 合法且根类型为对象。"""

        if value is None:
            return None
        return validate_object_schema(value, label="审批表单")


class ProcessResponse(BaseModel):
    """审批流概要响应。"""

    id: UUID
    name: str
    description: str | None
    status: str
    current_version_id: UUID | None
    current_version_no: int | None
    draft_version_id: UUID | None
    draft_version_no: int | None
    node_count: int
    created_at: datetime
    updated_at: datetime


class ProcessVersionResponse(BaseModel):
    """流程版本概要响应。"""

    id: UUID
    process_id: UUID
    version_no: int
    status: str
    name: str
    description: str | None
    revision: int
    node_count: int
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None


class ProcessGraphNodeResponse(BaseModel):
    """整图读取中的单个版本节点。"""

    id: UUID
    node_definition_id: UUID
    node_type: str
    node_definition_name: str | None
    name: str
    config: dict[str, Any]
    position: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ProcessGraphResponse(BaseModel):
    """版本整图读取响应。"""

    process_id: UUID
    version_id: UUID
    version_no: int
    version_status: str
    revision: int
    name: str
    description: str | None
    form_schema: dict[str, Any]
    form_ui_schema: dict[str, Any]
    orchestration: dict[str, Any]
    nodes: list[ProcessGraphNodeResponse]
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None


class ProcessValidationIssueResponse(BaseModel):
    """一条流程校验问题。"""

    model_config = ConfigDict(from_attributes=True)

    code: str
    message: str
    node_id: UUID | None = None
    field: str | None = None
    connection_index: int | None = None


class ProcessValidationResponse(BaseModel):
    """流程版本校验结果。"""

    process_id: UUID
    version_id: UUID
    valid: bool
    issues: list[ProcessValidationIssueResponse]

    @classmethod
    def build(
        cls,
        process_id: UUID,
        version_id: UUID,
        issues: Sequence[Any],
    ) -> "ProcessValidationResponse":
        """由校验问题列表构造版本校验响应。"""

        return cls(
            process_id=process_id,
            version_id=version_id,
            valid=not issues,
            issues=[
                ProcessValidationIssueResponse.model_validate(issue)
                for issue in issues
            ],
        )
