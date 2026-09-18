"""执行审批中心统一数据库初始化 SQL。"""

from pathlib import Path

from app.common.db.postgres_db import engine


# 初始化结构统一维护在 backend/data/init.sql 中，避免代码和 SQL 各维护一份。
INITIALIZATION_SQL_PATH = Path(__file__).resolve().parents[3] / "data" / "init.sql"


def load_initialization_statements() -> list[str]:
    """读取统一初始化 SQL，并拆分为可顺序执行的独立语句。"""

    sql_content = INITIALIZATION_SQL_PATH.read_text(encoding="utf-8")
    statements: list[str] = []

    # 当前初始化文件不包含函数体等带内部分号的结构，可以安全地按分号拆分。
    for raw_statement in sql_content.split(";"):
        normalized_statement = raw_statement.strip()
        if normalized_statement:
            statements.append(normalized_statement)

    return statements


def create_database_tables() -> None:
    """在同一事务中执行统一初始化 SQL。"""

    statements = load_initialization_statements()
    with engine.begin() as connection:
        # 顺序执行确保 Schema、表、外键和索引按文件中的依赖关系创建。
        for statement in statements:
            connection.exec_driver_sql(statement)


if __name__ == "__main__":
    create_database_tables()
    print(f"数据库初始化完成：{INITIALIZATION_SQL_PATH}")
