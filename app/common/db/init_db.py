"""执行审批中心统一数据库初始化 SQL。"""

from pathlib import Path

from sqlalchemy import inspect

from app.common.db.postgres_db import engine


# 初始化结构统一维护在 backend/data/init.sql 中，避免代码和 SQL 各维护一份。
INITIALIZATION_SQL_PATH = Path(__file__).resolve().parents[3] / "data" / "init.sql"

# 初始化完成后检查关键表，避免 SQL 执行成功但遗漏某个模块结构。
EXPECTED_SCHEMA_TABLES = {
    "tenant": {
        "person_binding",
        "tenant",
        "tenant_api_key",
        "tenant_callback_credential",
    },
    "organization": {
        "person",
        "department",
        "department_member",
    },
}


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


def verify_database_tables() -> dict[str, list[str]]:
    """检查初始化 SQL 要求的 Schema 和数据表是否已经存在。"""

    database_inspector = inspect(engine)
    existing_schemas = set(database_inspector.get_schema_names())
    verified_tables: dict[str, list[str]] = {}

    for schema_name, expected_tables in EXPECTED_SCHEMA_TABLES.items():
        if schema_name not in existing_schemas:
            raise RuntimeError(f"数据库缺少 Schema：{schema_name}")

        existing_tables = set(database_inspector.get_table_names(schema=schema_name))
        missing_tables = expected_tables - existing_tables
        if missing_tables:
            missing_table_names = ", ".join(sorted(missing_tables))
            raise RuntimeError(
                f"Schema {schema_name} 缺少数据表：{missing_table_names}"
            )

        verified_tables[schema_name] = sorted(existing_tables)

    return verified_tables


if __name__ == "__main__":
    create_database_tables()
    verified_schema_tables = verify_database_tables()
    print(f"数据库初始化完成：{INITIALIZATION_SQL_PATH}")
    for schema_name, table_names in verified_schema_tables.items():
        print(f"{schema_name}: {', '.join(table_names)}")
