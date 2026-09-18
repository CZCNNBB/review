from datetime import datetime

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    """用户服务的用户表模型。"""

    __tablename__ = "user"

    id: int = Field(primary_key=True, index=True)
    name: str
    email: str = Field(unique=True, index=True)
    password: str
    create_time: datetime = Field(default_factory=datetime.now)
    is_delete: str
