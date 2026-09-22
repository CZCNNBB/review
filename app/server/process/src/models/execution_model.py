"""业务执行记录数据库模型。

一条记录既表示待执行任务，也保存唯一一次 HTTP 调用结果。第一版没有多次重试，因此
不拆分 execution_job 和 execution_attempt。本表不保存 tenant_id，也不建立指向
tenant Schema 的外键：执行器通过 approval_instance_id 和租户使用记录确定租户，
这样关闭租户能力后审批运行模块仍然可以独立工作。
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


class BusinessExecutionRecord(SQLModel, table=True):
    """审批通过后的唯一一次业务系统调用及其结果。"""

    __tablename__ = "business_execution_record"
    __table_args__ = (
        # 同一个审批实例最多产生一条执行记录，数据库唯一约束是防止重复执行的最终保障。
        UniqueConstraint(
            "approval_instance_id",
            name="uq_business_execution_record_instance",
        ),
        {"schema": PROCESS_DB_SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    approval_instance_id: UUID = Field(
        foreign_key="process.approval_instance.id",
        index=True,
    )
    # 业务动作 ID 属于 integration Schema，不建立跨 Schema 外键。
    business_action_id: Optional[UUID] = Field(default=None, index=True)
    # 业务动作标识快照。即使后续动作配置被修改，本次已批准的调用方式也不变。
    action_code: str = Field(max_length=100, index=True)
    # 最终请求地址在后台执行器取得租户基础地址后再补齐。
    request_url: Optional[str] = Field(default=None, max_length=1000)
    # 以下五个字段是业务动作配置快照。业务动作在审批期间被删除时留空，由执行器判定
    # 为配置缺失失败，而不是让审批事务回滚。
    http_method: Optional[str] = Field(default=None, max_length=10)
    relative_path: Optional[str] = Field(default=None, max_length=500)
    success_status_codes_json: Optional[list] = Field(
        default=None,
        sa_type=PROCESS_JSON_TYPE,
    )
    timeout_ms: Optional[int] = Field(default=None)
    # 实际发送的参数在创建记录时固化，后续不再回头读取审批实例的实时数据。
    request_payload_json: dict = Field(
        default_factory=dict,
        sa_type=PROCESS_JSON_TYPE,
    )
    status: str = Field(default="PENDING", max_length=20, index=True)
    # 没有取得响应时状态码为空，例如网络异常或超时。
    http_status_code: Optional[int] = Field(default=None)
    # 响应正文按固定上限截断后保存。响应正文和错误摘要都不能包含认证请求头或 Token。
    response_body: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    error_message: Optional[str] = Field(default=None, max_length=1000)
    # 实际调用开始和结束时间。耗时通过两者相减计算，不重复保存 duration_ms。
    started_at: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    finished_at: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
