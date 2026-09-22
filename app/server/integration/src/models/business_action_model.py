"""业务动作定义数据库模型。

业务动作描述审批通过后可以执行的一类业务接口及其参数规则。该表不保存 tenant_id，
租户能否使用某个动作由 tenant.business_action_binding 决定，保证 integration 模块的
表结构不反向依赖租户模块。
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


# 业务接入模块使用独立的 integration Schema。
INTEGRATION_DB_SCHEMA = "integration"

# PostgreSQL 使用 JSONB，SQLite 测试环境使用通用 JSON，保证模型可以跨方言建表。
INTEGRATION_JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""

    return datetime.now(timezone.utc)


class BusinessAction(SQLModel, table=True):
    """审批通过后可以执行的一类业务动作及其参数规则。"""

    __tablename__ = "business_action"
    __table_args__ = (
        # action_code 是业务系统传值依据，必须全局唯一。
        UniqueConstraint("action_code", name="uq_business_action_code"),
        {"schema": INTEGRATION_DB_SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    action_code: str = Field(max_length=100, index=True)
    name: str = Field(max_length=128, index=True)
    description: Optional[str] = Field(default=None, max_length=500)
    # 第一版只支持 POST、PUT、PATCH，不允许业务请求动态指定调用方法。
    http_method: str = Field(default="POST", max_length=10)
    # 相对租户 callback_base_url 的路径，保存前必须确认它不是完整 URL。
    relative_path: str = Field(max_length=500)
    # execution_payload 的 JSON Schema，根类型必须是 object。
    request_schema_json: dict = Field(
        default_factory=dict,
        sa_type=INTEGRATION_JSON_TYPE,
    )
    # 空数组表示全部 2xx 视为调用成功。
    success_status_codes_json: list = Field(
        default_factory=list,
        sa_type=INTEGRATION_JSON_TYPE,
    )
    timeout_ms: int = Field(default=5000)
    status: str = Field(default="ENABLED", max_length=20, index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
