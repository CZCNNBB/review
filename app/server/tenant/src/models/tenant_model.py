"""租户、API Key 与回调签名凭据数据库模型。"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Text
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""

    return datetime.now(timezone.utc)


class Tenant(SQLModel, table=True):
    """接入审批中心的业务系统租户。"""

    __tablename__ = "tenant"

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

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
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

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    name: str = Field(max_length=100)
    key_id: str = Field(max_length=64, unique=True, index=True)
    # 回调签名时需要取回原始密钥，因此保存由应用主密钥加密后的密文，而不是不可逆哈希。
    secret_ciphertext: str = Field(sa_column=Column(Text, nullable=False))
    status: str = Field(default="ACTIVE", max_length=20, index=True)
    expires_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    revoked_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    created_by: Optional[UUID] = Field(default=None)
