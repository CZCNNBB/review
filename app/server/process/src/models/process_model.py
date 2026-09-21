"""审批流定义、节点能力和流程节点实例数据库模型。"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


# 审批流定义模块使用独立的 PostgreSQL Schema。
PROCESS_DB_SCHEMA = "process"

# 正式环境在 PostgreSQL 上落 JSONB。租户模块和人员组织模块的测试仍在 SQLite 上
# 用 SQLModel.metadata 建表，SQLite 无法渲染 JSONB，因此这里声明 PostgreSQL 变体
# 保证两种方言都能建表。
PROCESS_JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""

    return datetime.now(timezone.utc)


class NodeDefinition(SQLModel, table=True):
    """描述系统支持的节点能力和前端配置契约。

    本表不保存某条流程中的具体节点、审批人或位置。node_type 只表示后端执行分类，
    多个节点定义可以共用同一个 node_type，但拥有不同的名称、图标和配置 Schema。
    """

    __tablename__ = "node_definition"
    __table_args__ = {"schema": PROCESS_DB_SCHEMA}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    node_type: str = Field(max_length=32, index=True)
    # 名称在管理端作为节点能力的可读标识，数据库唯一约束负责兜住并发创建。
    name: str = Field(max_length=100, index=True, unique=True)
    description: Optional[str] = Field(default=None, max_length=500)
    icon: Optional[str] = Field(default=None, max_length=100)
    # 节点实例 config_json 必须满足的配置规则，由后端直接用于结构校验。
    config_schema_json: dict = Field(default_factory=dict, sa_type=PROCESS_JSON_TYPE)
    # 节点配置面板的展示规则，供前端渲染使用。
    ui_schema_json: dict = Field(default_factory=dict, sa_type=PROCESS_JSON_TYPE)
    status: str = Field(default="ENABLED", max_length=20, index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))


class ApprovalProcess(SQLModel, table=True):
    """一条完整审批流的当前定义。

    审批表单和流程编排都跟随流程一起创建、修改、复制和生成快照，因此不单独建立表。
    流程不提供物理删除，废弃流程设置为 DISABLED。
    """

    __tablename__ = "approval_process"
    __table_args__ = {"schema": PROCESS_DB_SCHEMA}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=128, index=True)
    description: Optional[str] = Field(default=None, max_length=500)
    status: str = Field(default="DRAFT", max_length=20, index=True)
    # 审批表单字段、类型、必填和校验规则，采用 JSON Schema 表述。
    form_schema_json: dict = Field(default_factory=dict, sa_type=PROCESS_JSON_TYPE)
    # 表单标签、顺序、分组和展示组件，采用 uiSchema 表述。
    form_ui_schema_json: dict = Field(default_factory=dict, sa_type=PROCESS_JSON_TYPE)
    # 节点关系和分支条件。分支属于流程编排能力，不建立 BRANCH 节点定义。
    orchestration_json: dict = Field(
        default_factory=lambda: {"connections": []},
        sa_type=PROCESS_JSON_TYPE,
    )
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))


class ApprovalProcessNode(SQLModel, table=True):
    """画布中的每一个具体节点实例。

    节点只关心自身能力和配置，不保存下一个节点或分支条件。id 由前端在拖入画布时
    生成，因此没有 default_factory，同一次完整流程保存请求可以直接在编排中引用新节点。
    """

    __tablename__ = "approval_process_node"
    __table_args__ = {"schema": PROCESS_DB_SCHEMA}

    id: UUID = Field(primary_key=True)
    process_id: UUID = Field(foreign_key="process.approval_process.id", index=True)
    node_definition_id: UUID = Field(foreign_key="process.node_definition.id", index=True)
    name: str = Field(max_length=128)
    # 当前节点实例的全部功能配置，审批模式和审批人都保存在这里。
    config_json: dict = Field(default_factory=dict, sa_type=PROCESS_JSON_TYPE)
    # 前端画布坐标。
    position_json: dict = Field(default_factory=dict, sa_type=PROCESS_JSON_TYPE)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
