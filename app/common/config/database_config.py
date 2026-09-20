"""审批中心 PostgreSQL 数据库配置。"""

import os

from dotenv import load_dotenv
from sqlalchemy.engine import URL

# 独立执行测试、初始化脚本时也需要主动加载 backend/.env。
# override=False 可以保留部署平台在进程环境中注入的同名变量。
load_dotenv(override=False)


def get_environment(name: str, default: str) -> str:
    """读取非空字符串环境变量，空值或未配置时使用默认值。"""

    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized_value = raw_value.strip()
    if not normalized_value:
        return default

    return normalized_value


def get_int_environment(name: str, default: int) -> int:
    """读取整数环境变量，空值或未配置时使用默认值。"""

    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default

    return int(raw_value)


# 初期只使用一个 PostgreSQL 数据库。配置统一集中在这里，避免各模块自行拼接地址。
postgres_db_CONFIG = {
    "host": get_environment("POSTGRES_HOST", "127.0.0.1"),
    "port": get_int_environment("POSTGRES_PORT", 5432),
    "username": get_environment("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
    "database": get_environment("POSTGRES_DATABASE", "approval_center"),
}

# 使用 SQLAlchemy URL 负责特殊字符转义，数据库密码包含 @、: 等字符时也能正确连接。
postgres_connection_string = URL.create(
    drivername="postgresql+psycopg2",
    username=postgres_db_CONFIG["username"],
    password=postgres_db_CONFIG["password"] or None,
    host=postgres_db_CONFIG["host"],
    port=postgres_db_CONFIG["port"],
    database=postgres_db_CONFIG["database"],
)

