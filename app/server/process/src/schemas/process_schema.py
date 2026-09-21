"""审批流定义、流程编排和校验结果的请求与响应模型。"""

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
    """创建审批流请求。

    创建后流程恒为草稿状态，因此请求模型不接收 status 字段，状态只通过启停接口迁移。
    """

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


class ProcessUpdateRequest(BaseModel):
    """更新审批流基本资料和审批表单请求。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=500)
    form_schema: dict[str, Any] | None = None
    form_ui_schema: dict[str, Any] | None = None

    @model_validator(mode="after")
    def ensure_non_empty_update(self) -> "ProcessUpdateRequest":
        """确保更新请求至少显式提供一个字段。"""

        if not self.model_fields_set:
            raise ValueError("至少需要提供一个更新字段")
        return self

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        """清理可选流程名称。"""

        if value is None:
            raise ValueError("流程名称不能设置为空")
        return normalize_required_text(value)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        """清理流程说明。"""

        return normalize_optional_text(value)

    @field_validator("form_schema")
    @classmethod
    def validate_form_schema(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        """校验审批表单 Schema 合法且根类型为对象。"""

        if value is None:
            return None
        return validate_object_schema(value, label="审批表单")


class ProcessGraphNodeRequest(BaseModel):
    """整图保存中的单个节点。

    id 由前端在把节点拖入画布时生成，后端不再重新分配，保证同一次保存请求里的
    编排数据可以直接引用新节点。
    """

    id: UUID
    node_definition_id: UUID
    name: str = Field(min_length=1, max_length=128)
    config: dict[str, Any] = Field(default_factory=dict)
    position: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """清理并校验节点实例名称。"""

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
    """整图保存请求，一次提交流程主体、完整节点列表和完整编排。"""

    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=500)
    # 缺省表示保留流程原有表单，避免前端漏传字段时把表单清空。
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
        """清理并校验流程名称。"""

        return normalize_required_text(value)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        """清理流程说明。"""

        return normalize_optional_text(value)

    @field_validator("form_schema")
    @classmethod
    def validate_form_schema(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        """校验审批表单 Schema 合法且根类型为对象。"""

        if value is None:
            return None
        return validate_object_schema(value, label="审批表单")


class ProcessResponse(BaseModel):
    """审批流概要响应，用于列表和详情。"""

    id: UUID
    name: str
    description: str | None
    status: str
    node_count: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def build(cls, process: Any, node_count: int) -> "ProcessResponse":
        """由流程模型和节点数量构造概要响应。"""

        return cls(
            id=process.id,
            name=process.name,
            description=process.description,
            status=process.status,
            node_count=node_count,
            created_at=process.created_at,
            updated_at=process.updated_at,
        )


class ProcessGraphNodeResponse(BaseModel):
    """整图读取中的单个节点，附带节点定义信息供画布直接渲染。"""

    id: UUID
    node_definition_id: UUID
    node_type: str | None
    node_definition_name: str | None
    name: str
    config: dict[str, Any]
    position: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ProcessGraphResponse(BaseModel):
    """整图读取响应，包含流程主体和完整编排。"""

    process_id: UUID
    name: str
    description: str | None
    status: str
    form_schema: dict[str, Any]
    form_ui_schema: dict[str, Any]
    orchestration: dict[str, Any]
    nodes: list[ProcessGraphNodeResponse]
    created_at: datetime
    updated_at: datetime


class ProcessValidationIssueResponse(BaseModel):
    """一条流程校验问题。"""

    model_config = ConfigDict(from_attributes=True)

    code: str
    message: str
    node_id: UUID | None = None
    field: str | None = None
    connection_index: int | None = None


class ProcessValidationResponse(BaseModel):
    """流程校验结果。"""

    process_id: UUID
    valid: bool
    issues: list[ProcessValidationIssueResponse]

    @classmethod
    def build(
        cls,
        process_id: UUID,
        issues: Sequence[Any],
    ) -> "ProcessValidationResponse":
        """由校验问题列表构造校验结果响应。"""

        return cls(
            process_id=process_id,
            valid=not issues,
            issues=[
                ProcessValidationIssueResponse.model_validate(issue)
                for issue in issues
            ],
        )
