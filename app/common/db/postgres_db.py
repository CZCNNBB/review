"""PostgreSQL 数据库引擎与会话工厂。"""

from sqlmodel import Session, create_engine
from app.common.config.database_config import postgres_connection_string


# 创建全局唯一的数据库引擎
# check_same_thread=False 仅用于 SQLite，PostgreSQL 不需要
engine = create_engine(
    postgres_connection_string,
    pool_pre_ping=True,  # 连接池健康检查
    pool_size=10,        # 连接池大小
    max_overflow=20,      # 最大溢出连接数
)


def get_postgres_engine():
    """为 FastAPI 请求提供数据库会话，并在请求结束后自动关闭。"""

    # 使用 with 语句保证接口正常返回或抛出异常时都能释放数据库连接。
    with Session(engine) as db:
        yield db


def get_db_session() -> Session:
    """创建普通函数使用的会话，调用者负责关闭该会话。"""

    return Session(engine)
