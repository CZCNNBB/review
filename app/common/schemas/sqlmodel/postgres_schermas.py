from datetime import datetime
from typing import Optional, Dict, Any
import time
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON, BigInteger
# 定义临时文件表
class TemporaryFile(SQLModel, table=True):
    __tablename__ = "temporary_file"

    id: str = Field(primary_key=True, index=True)
    name: str
    path: str
    size: float
    extension: str
    mime_type: str
    created_by: str
    created_at: str

# 定义聊天历史表
class ChatHistory(SQLModel, table=True):
    __tablename__ = "chat_history"

    id: int = Field(primary_key=True, index=True)
    session_id: str 
    role: str 
    content: str 
    create_time: datetime 

# 定义用户会话表
class User_Session(SQLModel, table=True):
    __tablename__ = "user_session"

    user_id: int = Field(foreign_key="user.id")
    session_id: str = Field(primary_key=True, index=True)
    session_title: str
    create_time: datetime = Field(default_factory = datetime.now)
    last_time: datetime = Field(default_factory = datetime.now)

# 定义用户表
class User(SQLModel, table=True):
    __tablename__ = "user"

    id: int = Field(primary_key=True, index=True)
    name: str
    email: str = Field(unique=True, index=True)
    password: str
    create_time: datetime = Field(default_factory = datetime.now)
    is_delete: str

# 定义向量集合表
class Langchain_Pg_Collection(SQLModel, table=True):
    __tablename__ = "langchain_pg_collection"

    uuid: str = Field(primary_key=True, index=True)
    name: str
    cmetadata: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))

# 定义模板表
class Templates(SQLModel, table=True):
    __tablename__ = "templates"

    id: str = Field(primary_key=True, index=True)
    category: str
    name: str
    prompt: str
    enabled: int
    created_at: int = Field(default_factory=lambda: int(time.time() * 1000), sa_column=Column(BigInteger))
    updated_at: int = Field(default_factory=lambda: int(time.time() * 1000), sa_column=Column(BigInteger))

# 定义分类表
class Categories(SQLModel, table=True):
    __tablename__ = "categories"

    category: str = Field(primary_key=True, index=True)
    icon: str
    pinned: int
    order_index: int
    color: str
    bg_color: str
    icon_color: str
    created_at: int = Field(default_factory=lambda: int(time.time() * 1000), sa_column=Column(BigInteger))
    updated_at: int = Field(default_factory=lambda: int(time.time() * 1000), sa_column=Column(BigInteger))
