"""文件元数据和审批附件关联模型。"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.server.process.src.models.process_model import utc_now


FILE_DB_SCHEMA = "file"


class FileRecord(SQLModel, table=True):
    """保存文件归属和对象存储位置，不把二进制内容写入数据库。"""

    __tablename__ = "file_record"
    __table_args__ = {"schema": FILE_DB_SCHEMA}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: Optional[UUID] = Field(default=None, index=True)
    object_key: str = Field(max_length=500, unique=True)
    file_name: str = Field(max_length=255)
    content_type: str = Field(max_length=150)
    size_bytes: int
    sha256: str = Field(max_length=64)
    status: str = Field(default="READY", max_length=20, index=True)
    uploaded_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))


class ApprovalAttachment(SQLModel, table=True):
    """把一份不可变文件按顺序关联到一个审批实例。"""

    __tablename__ = "approval_attachment"
    __table_args__ = (
        UniqueConstraint("approval_instance_id", "file_id", name="uq_approval_attachment_file"),
        {"schema": FILE_DB_SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    file_id: UUID = Field(foreign_key="file.file_record.id", index=True)
    approval_instance_id: UUID = Field(index=True)
    position: int
    attached_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
