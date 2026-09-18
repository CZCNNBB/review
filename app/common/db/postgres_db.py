# ----------------postgres数据库操作-------------------
from sqlmodel import Session, create_engine
from app.common.config.datebase_config import postgres_connection_string


# 创建全局唯一的数据库引擎
# check_same_thread=False 仅用于 SQLite，PostgreSQL 不需要
engine = create_engine(
    postgres_connection_string,
    pool_pre_ping=True,  # 连接池健康检查
    pool_size=10,        # 连接池大小
    max_overflow=20,      # 最大溢出连接数
)


def get_postgres_engine(): 
    """
    FastAPI 依赖注入使用的生成器
    """
    # 使用with语句确保数据库会话在请求结束后自动关闭
    with Session(engine) as db:
        yield db


def get_db_session() -> Session:
    """
    普通函数调用使用的 Session 工厂
    注意：调用者需要手动关闭 Session (使用 with 语句或 .close())
    """
    return Session(engine)
        

# if __name__ == "__main__":
#     # 测试数据库连接
#     postgres_db_CONFIG = {
#     "host": "192.168.8.151",
#     "port": 5432,
#     "username": "remote_super",
#     "password": "himice2024",
#     "database": "agent",
# }

#     connection_string = f"postgresql://{postgres_db_CONFIG['username']}:{postgres_db_CONFIG['password']}@{postgres_db_CONFIG['host']}:{postgres_db_CONFIG['port']}/{postgres_db_CONFIG['database']}"
#     manager = PostgresDatabase(connection_string)
#     print(manager.get_table_name())
#     print(manager.insert_file_info({
#         "id": "123456",
#         "name": "test.txt",
#         "path": "/tmp/test.txt",
#         "out_time": "2024-01-01",
#         "size": 1024,
#         "extension": "txt",
#         "mime_type": "text/plain",
#         "created_by": "user123",
#         "created_at": "2024-01-01 00:00:00"
#     }))
#     print(manager.get_file_info("123456"))
