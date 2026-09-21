"""审批实例、节点执行、审批任务和时间线的请求响应模型。"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.server.process.src.schemas.process_schema import (
    normalize_optional_text,
    normalize_required_text,
)


class ApprovalStartRequest(BaseModel):
    """业务系统发起审批的请求。

    业务系统只传稳定的业务单据标识和审批数据，实际使用的流程版本由审批中心按
    流程当前已发布版本自动确定。
    """

    business_key: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    applicant_person_id: UUID | None = None
    action_code: str | None = Field(default=None, max_length=100)
    approval_form: dict[str, Any] = Field(default_factory=dict)
    execution_payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("business_key")
    @classmethod
    def normalize_business_key(cls, value: str) -> str:
        """清理并校验业务单据标识。"""

        return normalize_required_text(value)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        """清理并校验审批单标题。"""

        return normalize_required_text(value)

    @field_validator("action_code")
    @classmethod
    def normalize_action_code(cls, value: str | None) -> str | None:
        """清理业务动作标识，空字符串统一保存为 None。"""

        return normalize_optional_text(value)


class ApprovalTaskActionRequest(BaseModel):
    """同意或拒绝审批任务的请求。

    接入可信登录身份前，操作人由调用方显式传递，接口层校验任务确实分配给了该人员。
    """

    person_id: UUID
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        """清理审批意见，纯空白视为没有填写。"""

        return normalize_optional_text(value)


class ApprovalNodeExecutionResponse(BaseModel):
    """实例实际经过的一个节点。"""

    id: UUID
    node_id: UUID
    node_type: str
    node_name: str
    sequence_no: int
    status: str
    entered_at: datetime
    completed_at: datetime | None
    duration_ms: int | None
    next_node_id: UUID | None
    next_node_name: str | None
    condition_hit: bool | None
    result: dict[str, Any]


class ApprovalTaskResponse(BaseModel):
    """一位审批人在某个节点上的待办任务。"""

    id: UUID
    instance_id: UUID
    node_execution_id: UUID
    instance_title: str | None
    business_key: str | None
    node_name: str | None
    approver_person_id: UUID
    approver_snapshot: dict[str, Any]
    status: str
    created_at: datetime
    handled_at: datetime | None
    cancelled_at: datetime | None
    duration_ms: int | None


class ApprovalRecordResponse(BaseModel):
    """一次审批操作留下的审计记录。"""

    id: UUID
    instance_id: UUID
    node_execution_id: UUID
    task_id: UUID
    operator_person_id: UUID
    operator_snapshot: dict[str, Any]
    action: str
    comment: str | None
    created_at: datetime
    duration_ms: int | None


class ApprovalTimelineEntryResponse(BaseModel):
    """时间线中的一条节点记录，连同该节点产生的任务和审批记录。"""

    node_execution: ApprovalNodeExecutionResponse
    tasks: list[ApprovalTaskResponse]
    records: list[ApprovalRecordResponse]


class ApprovalTimelineResponse(BaseModel):
    """审批实例的完整运行时间线。"""

    instance_id: UUID
    title: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    entries: list[ApprovalTimelineEntryResponse]


class ApprovalInstanceDetailResponse(BaseModel):
    """审批详情，供后台详情页展示运行状态和处理过程。"""

    id: UUID
    process_id: UUID
    process_name: str
    process_version_id: UUID
    process_version_no: int
    business_key: str
    title: str
    applicant_person_id: UUID | None
    applicant_snapshot: dict[str, Any]
    action_code: str | None
    status: str
    approval_form: dict[str, Any]
    current_node: ApprovalNodeExecutionResponse | None
    node_executions: list[ApprovalNodeExecutionResponse]
    tasks: list[ApprovalTaskResponse]
    records: list[ApprovalRecordResponse]
    pending_tasks: list[ApprovalTaskResponse]
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    created_at: datetime
    updated_at: datetime


class ApprovalInstanceStartedResponse(BaseModel):
    """发起审批的响应。

    重复发起同一个幂等键时返回原审批实例，此时 idempotent_replay 为真，业务系统
    可以据此判断本次请求是否真正创建了新实例。
    """

    instance_id: UUID
    status: str
    process_id: UUID
    process_version_id: UUID
    process_version_no: int
    current_node_name: str | None
    pending_approver_person_ids: list[UUID]
    started_at: datetime
    idempotent_replay: bool


class ApprovalActionResponse(BaseModel):
    """同意或拒绝任务后返回的最新状态。"""

    instance_id: UUID
    instance_status: str
    task_id: UUID
    task_status: str
    node_execution_id: UUID
    node_execution_status: str
    current_node_name: str | None
    # 重复提交相同结果时返回原结果，不再写入新的审批记录。
    idempotent_replay: bool
