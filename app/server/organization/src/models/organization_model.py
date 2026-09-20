"""全局人员、部门与人员部门关系数据库模型。"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel


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
    mobile: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    status: str = Field(default="ENABLED", max_length=20, index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))


class Department(SQLModel, table=True):
    """与租户无关的全局平铺部门。"""

    __tablename__ = "department"
    __table_args__ = {"schema": ORGANIZATION_DB_SCHEMA}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    code: str = Field(max_length=64, unique=True, index=True)
    name: str = Field(max_length=100)
    status: str = Field(default="ENABLED", max_length=20, index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))


class DepartmentMember(SQLModel, table=True):
    """全局人员与部门之间的业务关系。"""

    __tablename__ = "department_member"
    __table_args__ = (
        UniqueConstraint(
            "department_id",
            "person_id",
            name="uq_department_member_person",
        ),
        {"schema": ORGANIZATION_DB_SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    department_id: UUID = Field(
        foreign_key="organization.department.id",
        index=True,
    )
    person_id: UUID = Field(foreign_key="organization.person.id", index=True)
    status: str = Field(default="ENABLED", max_length=20, index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))

