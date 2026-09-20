"""人员、部门与租户成员数据库模型。"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel


# 每个 server 使用独立的 PostgreSQL Schema。
ORGANIZATION_DB_SCHEMA = "organization"


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""

    return datetime.now(timezone.utc)


class Person(SQLModel, table=True):
    """审批中心能够识别的全局人员。"""

    __tablename__ = "person"
    __table_args__ = {"schema": ORGANIZATION_DB_SCHEMA}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=100, index=True)
    mobile: Optional[str] = Field(default=None, max_length=32)
    email: Optional[str] = Field(default=None, max_length=255)
    status: str = Field(default="ENABLED", max_length=20, index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))


class Department(SQLModel, table=True):
    """租户内部的平铺部门。"""

    __tablename__ = "department"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_department_tenant_code"),
        {"schema": ORGANIZATION_DB_SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.tenant.id", index=True)
    code: str = Field(max_length=64)
    name: str = Field(max_length=100)
    status: str = Field(default="ENABLED", max_length=20, index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))


class TenantMember(SQLModel, table=True):
    """人员与租户之间的成员关系。"""

    __tablename__ = "tenant_member"
    __table_args__ = (
        UniqueConstraint("tenant_id", "person_id", name="uq_tenant_member_person"),
        UniqueConstraint("tenant_id", "employee_no", name="uq_tenant_member_employee_no"),
        UniqueConstraint(
            "tenant_id",
            "external_user_id",
            name="uq_tenant_member_external_user",
        ),
        {"schema": ORGANIZATION_DB_SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.tenant.id", index=True)
    person_id: UUID = Field(foreign_key="organization.person.id", index=True)
    department_id: Optional[UUID] = Field(
        default=None,
        foreign_key="organization.department.id",
        index=True,
    )
    employee_no: Optional[str] = Field(default=None, max_length=64)
    external_user_id: Optional[str] = Field(default=None, max_length=128)
    display_name: Optional[str] = Field(default=None, max_length=100)
    status: str = Field(default="ENABLED", max_length=20, index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))

