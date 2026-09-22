"""租户、API Key、回调凭据与人员绑定数据库模型。"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


# 每个 server 使用独立的 PostgreSQL Schema；租户模块统一放在 tenant 下。
TENANT_DB_SCHEMA = "tenant"


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""

    return datetime.now(timezone.utc)


class Tenant(SQLModel, table=True):
    """接入审批中心的业务系统租户。"""

    __tablename__ = "tenant"
    __table_args__ = {"schema": TENANT_DB_SCHEMA}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    code: str = Field(max_length=64, unique=True, index=True)
    name: str = Field(max_length=128)
    description: Optional[str] = Field(default=None, max_length=500)
    callback_base_url: str = Field(max_length=500)
    status: str = Field(default="ENABLED", max_length=20, index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))


class TenantApiKey(SQLModel, table=True):
    """业务系统调用审批 API 使用的 API Key。"""

    __tablename__ = "tenant_api_key"
    __table_args__ = {"schema": TENANT_DB_SCHEMA}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.tenant.id", index=True)
    name: str = Field(max_length=100)
    # 第一版按项目约定直接保存完整明文，便于管理页面查询和复制。
    api_key: str = Field(max_length=128, unique=True, index=True)
    status: str = Field(default="ACTIVE", max_length=20, index=True)
    expires_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    last_used_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    revoked_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    created_by: Optional[UUID] = Field(default=None)


class TenantCallbackCredential(SQLModel, table=True):
    """审批中心向业务系统发送回调时使用的签名凭据。"""

    __tablename__ = "tenant_callback_credential"
    __table_args__ = {"schema": TENANT_DB_SCHEMA}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.tenant.id", index=True)
    name: str = Field(max_length=100)
    key_id: str = Field(max_length=64, unique=True, index=True)
    # 回调签名时需要取回原始密钥，因此保存由应用主密钥加密后的密文。
    secret_ciphertext: str = Field(sa_column=Column(Text, nullable=False))
    status: str = Field(default="ACTIVE", max_length=20, index=True)
    expires_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    revoked_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    created_by: Optional[UUID] = Field(default=None)


class PersonBinding(SQLModel, table=True):
    """租户与全局人员之间的绑定及租户内人员资料。"""

    __tablename__ = "person_binding"
    __table_args__ = (
        UniqueConstraint("tenant_id", "person_id", name="uq_person_binding_resource"),
        UniqueConstraint("tenant_id", "employee_no", name="uq_person_binding_employee_no"),
        UniqueConstraint(
            "tenant_id",
            "external_user_id",
            name="uq_person_binding_external_user",
        ),
        {"schema": TENANT_DB_SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.tenant.id", index=True)
    # 业务资源 ID 不建立跨 Schema 外键，保证 tenant Schema 可以独立移除。
    person_id: UUID = Field(index=True)
    employee_no: Optional[str] = Field(default=None, max_length=64)
    external_user_id: Optional[str] = Field(default=None, max_length=128)
    display_name: Optional[str] = Field(default=None, max_length=100)
    status: str = Field(default="ENABLED", max_length=20, index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))


class ProcessBinding(SQLModel, table=True):
    """租户可以使用的审批流授权。"""

    __tablename__ = "process_binding"
    __table_args__ = (
        # 一个租户对同一条审批流只保留一条授权记录，停用后重新启用即可。
        UniqueConstraint(
            "tenant_id",
            "process_id",
            name="uq_process_binding_resource",
        ),
        {"schema": TENANT_DB_SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.tenant.id", index=True)
    # 审批流 ID 不建立跨 Schema 外键，保证 tenant Schema 可以独立移除。
    process_id: UUID = Field(index=True)
    status: str = Field(default="ENABLED", max_length=20, index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))


class BusinessActionBinding(SQLModel, table=True):
    """租户可以使用的业务动作授权。"""

    __tablename__ = "business_action_binding"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "business_action_id",
            name="uq_business_action_binding_resource",
        ),
        {"schema": TENANT_DB_SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.tenant.id", index=True)
    # 业务动作 ID 不建立跨 Schema 外键，保证 tenant Schema 可以独立移除。
    business_action_id: UUID = Field(index=True)
    status: str = Field(default="ENABLED", max_length=20, index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))


class ProcessUsageRecord(SQLModel, table=True):
    """租户发起审批的使用记录，同时是审批实例的租户归属入口。

    该表只保存归属和关联信息。审批状态、当前节点和耗时统一从 process 运行表读取，
    不在这里重复保存，避免同一份状态出现两份不一致的副本。
    """

    __tablename__ = "process_usage_record"
    __table_args__ = (
        # 一个审批实例只属于一个租户。
        UniqueConstraint(
            "approval_instance_id",
            name="uq_process_usage_record_instance",
        ),
        # 同一租户对同一流程下的同一业务单据只允许发起一次审批。
        UniqueConstraint(
            "tenant_id",
            "process_id",
            "business_key",
            name="uq_process_usage_record_business_key",
        ),
        {"schema": TENANT_DB_SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.tenant.id", index=True)
    process_id: UUID = Field(index=True)
    process_version_id: UUID
    approval_instance_id: UUID = Field(index=True)
    business_key: str = Field(max_length=200, index=True)
    # 审批通过后需要执行的业务动作，为空表示只完成审批不触发业务执行。
    action_code: Optional[str] = Field(default=None, max_length=100, index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
