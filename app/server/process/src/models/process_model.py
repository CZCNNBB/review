"""审批流节点能力、流程主体、流程版本和版本节点数据库模型。"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


# 审批流定义和后续运行数据统一使用 process Schema。
PROCESS_DB_SCHEMA = "process"

# PostgreSQL 使用 JSONB，SQLite 测试环境使用通用 JSON，保证模型可以跨方言建表。
PROCESS_JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""

    return datetime.now(timezone.utc)


class NodeDefinition(SQLModel, table=True):
    """描述系统支持的公共节点能力和前端配置契约。"""

    __tablename__ = "node_definition"
    __table_args__ = {"schema": PROCESS_DB_SCHEMA}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    node_type: str = Field(max_length=32, index=True)
    # 名称是管理端可读标识，数据库唯一约束负责处理并发重名。
    name: str = Field(max_length=100, index=True, unique=True)
    description: Optional[str] = Field(default=None, max_length=500)
    icon: Optional[str] = Field(default=None, max_length=100)
    config_schema_json: dict = Field(default_factory=dict, sa_type=PROCESS_JSON_TYPE)
    ui_schema_json: dict = Field(default_factory=dict, sa_type=PROCESS_JSON_TYPE)
    status: str = Field(default="ENABLED", max_length=20, index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))


class ApprovalProcess(SQLModel, table=True):
    """保存审批流稳定身份、启停状态和当前已发布版本。"""

    __tablename__ = "approval_process"
    __table_args__ = {"schema": PROCESS_DB_SCHEMA}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    # 名称与说明用于列表快速展示，发布版本时从版本主体同步更新。
    name: str = Field(max_length=128, index=True)
    description: Optional[str] = Field(default=None, max_length=500)
    status: str = Field(default="DRAFT", max_length=20, index=True)
    current_version_id: Optional[UUID] = Field(
        default=None,
        foreign_key="process.approval_process_version.id",
        index=True,
    )
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))


class ApprovalProcessVersion(SQLModel, table=True):
    """保存一版不可分割的流程表单和编排主体。"""

    __tablename__ = "approval_process_version"
    __table_args__ = {"schema": PROCESS_DB_SCHEMA}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    process_id: UUID = Field(foreign_key="process.approval_process.id", index=True)
    version_no: int = Field(ge=1)
    status: str = Field(default="DRAFT", max_length=20, index=True)
    name: str = Field(max_length=128)
    description: Optional[str] = Field(default=None, max_length=500)
    form_schema_json: dict = Field(default_factory=dict, sa_type=PROCESS_JSON_TYPE)
    form_ui_schema_json: dict = Field(default_factory=dict, sa_type=PROCESS_JSON_TYPE)
    orchestration_json: dict = Field(
        default_factory=lambda: {"connections": []},
        sa_type=PROCESS_JSON_TYPE,
    )
    # revision 用于整图保存的乐观锁，避免两个编辑者静默覆盖彼此修改。
    revision: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    published_at: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )


class ApprovalProcessVersionNode(SQLModel, table=True):
    """保存某个流程版本画布中的具体节点及其冻结配置。"""

    __tablename__ = "approval_process_version_node"
    __table_args__ = {"schema": PROCESS_DB_SCHEMA}

    # 节点 ID 由前端创建；复制版本时由后端重新生成并重写编排引用。
    id: UUID = Field(primary_key=True)
    process_version_id: UUID = Field(
        foreign_key="process.approval_process_version.id",
        index=True,
    )
    node_definition_id: UUID = Field(
        foreign_key="process.node_definition.id",
        index=True,
    )
    # 固化执行类型，使已发布版本不依赖节点定义后续变化。
    node_type: str = Field(max_length=32, index=True)
    name: str = Field(max_length=128)
    config_json: dict = Field(default_factory=dict, sa_type=PROCESS_JSON_TYPE)
    position_json: dict = Field(default_factory=dict, sa_type=PROCESS_JSON_TYPE)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
