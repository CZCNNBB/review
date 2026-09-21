"""统一初始化 SQL 的结构测试。

data/init.sql 是数据库结构的唯一来源，由人工在数据库客户端执行，应用代码不再
包含任何建库动作。测试在这里提前拦住两类问题：脚本被写坏导致无法整体执行，以及
seed 节点定义缺失或内容不正确。
"""

import unittest

from tests.process_test_helpers import (
    INITIALIZATION_SQL_PATH,
    load_seed_node_definitions,
)


def split_sql_statements(sql_content: str) -> list[str]:
    """按分号拆分初始化脚本，用于断言脚本可以逐条执行。

    有些数据库客户端会按分号拆分脚本后逐条提交，因此 seed 语句内部不要出现分号。
    """

    return [
        statement.strip()
        for statement in sql_content.split(";")
        if statement.strip()
    ]


class InitializationSqlTestCase(unittest.TestCase):
    """验证审批流相关的建表语句和 seed 数据。"""

    def setUp(self) -> None:
        """读取初始化脚本内容。"""

        self.sql_content = INITIALIZATION_SQL_PATH.read_text(encoding="utf-8")
        self.statements = split_sql_statements(self.sql_content)

    def test_script_can_be_split_into_statements(self) -> None:
        """脚本可以拆分出非空语句，且只包含可执行语句。"""

        self.assertTrue(self.statements)
        for statement in self.statements:
            head = statement.split(None, 1)[0].upper()
            self.assertIn(head, {"CREATE", "ALTER", "INSERT", "COMMENT", "--"})

    def test_script_has_no_dollar_quoted_block(self) -> None:
        """脚本不能包含 DO $$ 块，否则按分号拆分会被破坏。"""

        self.assertNotIn("DO $$", self.sql_content)

    def test_application_code_does_not_initialize_database(self) -> None:
        """应用代码不包含建库动作，数据库结构只由 init.sql 维护。"""

        database_package = (
            INITIALIZATION_SQL_PATH.parents[1] / "app" / "common" / "db"
        )
        python_files = sorted(database_package.glob("*.py"))
        self.assertTrue(python_files)

        for python_file in python_files:
            source = python_file.read_text(encoding="utf-8")
            self.assertNotIn("create_all", source, python_file.name)
            self.assertNotIn("CREATE TABLE", source, python_file.name)
            self.assertNotIn("exec_driver_sql", source, python_file.name)
            self.assertNotIn("init.sql", source, python_file.name)

    def test_process_schema_and_tables_are_declared(self) -> None:
        """脚本声明了 process Schema 和四张流程定义表。"""

        self.assertIn("CREATE SCHEMA IF NOT EXISTS process", self.sql_content)
        for table_name in (
            "process.node_definition",
            "process.approval_process",
            "process.approval_process_version",
            "process.approval_process_version_node",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table_name}", self.sql_content)

    def test_json_columns_use_jsonb(self) -> None:
        """审批流表的 JSON 列使用 JSONB。"""

        for column_name in (
            "config_schema_json JSONB",
            "ui_schema_json JSONB",
            "form_schema_json JSONB",
            "form_ui_schema_json JSONB",
            "orchestration_json JSONB",
            "config_json JSONB",
            "position_json JSONB",
        ):
            self.assertIn(column_name, self.sql_content)

    def test_node_definition_name_has_unique_index(self) -> None:
        """节点定义名称由数据库唯一索引兜住并发创建。"""

        self.assertIn(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_process_node_definition_name",
            self.sql_content,
        )

    def test_process_tables_and_columns_have_comments(self) -> None:
        """审批流四张表和关键字段都带注释。"""

        for table_name in (
            "process.node_definition",
            "process.approval_process",
            "process.approval_process_version",
            "process.approval_process_version_node",
        ):
            self.assertIn(f"COMMENT ON TABLE {table_name} IS", self.sql_content)
            self.assertIn(
                f"COMMENT ON COLUMN {table_name}.id IS",
                self.sql_content,
            )

    def test_process_version_constraints_are_declared(self) -> None:
        """版本号、单草稿和当前版本关系由数据库约束兜底。"""

        self.assertIn("UNIQUE (process_id, version_no)", self.sql_content)
        self.assertIn(
            "ux_process_approval_process_version_one_draft",
            self.sql_content,
        )
        self.assertIn("ADD COLUMN IF NOT EXISTS current_version_id UUID", self.sql_content)

    def test_empty_table_upgrade_script_has_data_guard(self) -> None:
        """一次性升级脚本必须在删除旧表前拒绝非空流程表。"""

        migration_path = (
            INITIALIZATION_SQL_PATH.parent
            / "migrations"
            / "20260921_process_version_upgrade.sql"
        )
        migration_content = migration_path.read_text(encoding="utf-8")
        self.assertIn("IF EXISTS (SELECT 1 FROM process.approval_process", migration_content)
        self.assertIn("RAISE EXCEPTION", migration_content)
        self.assertIn("DROP TABLE IF EXISTS process.approval_process_node", migration_content)

    def test_process_binding_table_is_not_created_yet(self) -> None:
        """租户流程授权表推迟到租户模块实现，本次不建表。"""

        self.assertNotIn("tenant.process_binding", self.sql_content)

    def test_seed_node_definitions_are_complete(self) -> None:
        """seed 注册了 START、APPROVAL、END 三种节点能力。"""

        definitions = load_seed_node_definitions()
        self.assertEqual(set(definitions), {"START", "APPROVAL", "END"})

        expected_ids = {
            "START": "00000000-0000-0000-0000-000000000101",
            "APPROVAL": "00000000-0000-0000-0000-000000000102",
            "END": "00000000-0000-0000-0000-000000000103",
        }
        for node_type, definition in definitions.items():
            self.assertEqual(str(definition.id), expected_ids[node_type])
            self.assertEqual(definition.status, "ENABLED")

    def test_seed_statement_is_idempotent(self) -> None:
        """seed 使用 ON CONFLICT DO NOTHING，重复执行不会失败。"""

        seed_statement = next(
            statement
            for statement in self.statements
            if "INSERT INTO process.node_definition" in statement
        )
        self.assertIn("ON CONFLICT (id) DO NOTHING", seed_statement)

    def test_seed_config_schemas_declare_required_config(self) -> None:
        """审批和结束节点的配置 Schema 声明了必填项。"""

        definitions = load_seed_node_definitions()

        approval_schema = definitions["APPROVAL"].config_schema_json
        self.assertEqual(
            sorted(approval_schema["required"]),
            ["approval_mode", "approvers"],
        )
        self.assertEqual(
            approval_schema["properties"]["approval_mode"]["enum"],
            ["AND", "OR"],
        )
        self.assertEqual(
            approval_schema["properties"]["approvers"]["minItems"],
            1,
        )

        end_schema = definitions["END"].config_schema_json
        self.assertEqual(end_schema["required"], ["result_status"])
        self.assertEqual(
            end_schema["properties"]["result_status"]["enum"],
            ["APPROVED", "REJECTED"],
        )


if __name__ == "__main__":
    unittest.main()
