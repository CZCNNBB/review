"""开发环境数据库表初始化入口。"""

from sqlmodel import SQLModel

from app.common.db.postgres_db import engine
# 显式导入各模块模型，确保 SQLModel.metadata 已完成表注册。
from app.server.tenant.src.models import Tenant, TenantApiKey, TenantCallbackCredential
from app.server.user.src.models.user_model import User


def create_database_tables() -> None:
    """创建当前已注册但尚不存在的数据库表。"""

    # create_all 只适合开发期初始化；正式环境结构变更应切换到数据库迁移工具。
    SQLModel.metadata.create_all(engine)


if __name__ == "__main__":
    create_database_tables()
    print("数据库表初始化完成")
