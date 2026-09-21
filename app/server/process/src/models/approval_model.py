"""审批实例、节点执行、审批任务和审批记录数据库模型。

四张运行表属于 process Schema，与流程定义共用同一个模块。运行表只保存审批自身
的数据，不保存 tenant_id，也不建立指向 tenant Schema 的外键。
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.server.process.src.models.process_model import (
    PROCESS_DB_SCHEMA,
    PROCESS_JSON_TYPE,
    utc_now,
)


class ApprovalInstance(SQLModel, table=True):
    """一次完整的审批申请，同时持久化审批单数据和业务执行参数。"""

    __tablename__ = "approval_instance"
    __table_args__ = (
        # 内部幂等键全局唯一，保证重复发起返回同一个审批实例。
        UniqueConstraint(
            "idempotency_key",
            name="uq_approval_instance_idempotency_key",
        ),
        {"schema": PROCESS_DB_SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    process_id: UUID = Field(foreign_key="process.approval_process.id", index=True)
    # 绑定发起时确定的已发布版本，后续发布新版本不影响本实例。
    process_version_id: UUID = Field(
        foreign_key="process.approval_process_version.id",
        index=True,
    )
    business_key: str = Field(max_length=200, index=True)
    idempotency_key: str = Field(max_length=200, index=True)
    # 发起请求内容的规范化摘要，用于判断同一业务单据的重复发起是否携带了相同内容。
    request_digest: Optional[str] = Field(default=None, max_length=64)
    title: str = Field(max_length=200)
    # 人员 ID 不建立指向 organization Schema 的跨 Schema 外键。
    applicant_person_id: Optional[UUID] = Field(default=None, index=True)
    applicant_snapshot_json: dict = Field(
        default_factory=dict,
        sa_type=PROCESS_JSON_TYPE,
    )
    # 审批单展示数据与业务执行参数分开保存，用途和审计范围都不同。
    approval_form_json: dict = Field(default_factory=dict, sa_type=PROCESS_JSON_TYPE)
    execution_payload_json: dict = Field(
        default_factory=dict,
        sa_type=PROCESS_JSON_TYPE,
    )
    action_code: Optional[str] = Field(default=None, max_length=100)
    status: str = Field(default="RUNNING", max_length=20, index=True)
    # 指向实例当前停留的活动节点执行记录，结束时清空。
    current_node_execution_id: Optional[UUID] = Field(default=None, index=True)
    started_at: datetime = Field(
        default_factory=utc_now,
        sa_type=DateTime(timezone=True),
    )
    finished_at: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))


class ApprovalNodeExecution(SQLModel, table=True):
    """实例实际进入过的节点，同时记录当前运行位置和实际选择的路径。"""

    __tablename__ = "approval_node_execution"
    __table_args__ = (
        # 实际执行顺序在实例内唯一，作为时间线排序依据。
        UniqueConstraint(
            "instance_id",
            "sequence_no",
            name="uq_approval_node_execution_sequence",
        ),
        {"schema": PROCESS_DB_SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    instance_id: UUID = Field(foreign_key="process.approval_instance.id", index=True)
    process_version_id: UUID = Field(
        foreign_key="process.approval_process_version.id",
        index=True,
    )
    node_id: UUID = Field(foreign_key="process.approval_process_version_node.id", index=True)
    # 执行类型和名称在进入节点时固化，节点定义后续变化不影响历史记录。
    node_type: str = Field(max_length=32, index=True)
    node_name: str = Field(max_length=128)
    sequence_no: int = Field(ge=1)
    status: str = Field(default="ACTIVE", max_length=20, index=True)
    entered_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    completed_at: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    # 实际选择的后续节点，条件分支命中情况保存在 result_json 中。
    next_node_id: Optional[UUID] = Field(default=None)
    result_json: dict = Field(default_factory=dict, sa_type=PROCESS_JSON_TYPE)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))


class ApprovalTask(SQLModel, table=True):
    """进入人工审批节点时，为全部审批人同时创建的待办任务。"""

    __tablename__ = "approval_task"
    __table_args__ = (
        # 同一节点执行内不给同一审批人重复创建任务。
        UniqueConstraint(
            "node_execution_id",
            "approver_person_id",
            name="uq_approval_task_approver",
        ),
        {"schema": PROCESS_DB_SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    instance_id: UUID = Field(foreign_key="process.approval_instance.id", index=True)
    node_execution_id: UUID = Field(
        foreign_key="process.approval_node_execution.id",
        index=True,
    )
    # 审批人 ID 不建立指向 organization Schema 的跨 Schema 外键。
    approver_person_id: UUID = Field(index=True)
    approver_snapshot_json: dict = Field(
        default_factory=dict,
        sa_type=PROCESS_JSON_TYPE,
    )
    status: str = Field(default="PENDING", max_length=20, index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    handled_at: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    cancelled_at: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))


class ApprovalRecord(SQLModel, table=True):
    """审批人的实际操作，是不可修改的审计记录。"""

    __tablename__ = "approval_record"
    __table_args__ = (
        # 第一版一个任务只能产生一条最终审批记录。
        UniqueConstraint("task_id", name="uq_approval_record_task"),
        {"schema": PROCESS_DB_SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    instance_id: UUID = Field(foreign_key="process.approval_instance.id", index=True)
    node_execution_id: UUID = Field(
        foreign_key="process.approval_node_execution.id",
        index=True,
    )
    task_id: UUID = Field(foreign_key="process.approval_task.id", index=True)
    operator_person_id: UUID = Field(index=True)
    operator_snapshot_json: dict = Field(
        default_factory=dict,
        sa_type=PROCESS_JSON_TYPE,
    )
    action: str = Field(max_length=20, index=True)
    # 审批意见长度不受限，使用 TEXT 而不是带长度的字符串。
    comment: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
