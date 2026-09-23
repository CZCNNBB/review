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

    def test_business_access_tables_are_declared(self) -> None:
        """业务接入模块的四张表已建好，且不再另建含义重复的实例绑定表。"""

        for table_name in (
            "tenant.process_binding",
            "tenant.business_action_binding",
            "tenant.process_usage_record",
            "integration.business_action",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table_name}", self.sql_content)

        self.assertNotIn("approval_instance_binding", self.sql_content)

    def test_business_access_tables_and_columns_have_comments(self) -> None:
        """业务接入表和它自己的字段都带注释。"""

        for table_name in (
            "tenant.process_binding",
            "tenant.business_action_binding",
            "tenant.process_usage_record",
            "integration.business_action",
        ):
            self.assertIn(f"COMMENT ON TABLE {table_name} IS", self.sql_content)
            self.assertIn(f"COMMENT ON COLUMN {table_name}.id IS", self.sql_content)

    def test_business_access_unique_constraints_are_declared(self) -> None:
        """幂等和授权唯一性由数据库约束兜住，不只依赖代码查询。"""

        self.assertIn("UNIQUE (tenant_id, process_id)", self.sql_content)
        self.assertIn("UNIQUE (tenant_id, business_action_id)", self.sql_content)
        self.assertIn("UNIQUE (approval_instance_id)", self.sql_content)
        self.assertIn("UNIQUE (tenant_id, process_id, business_key)", self.sql_content)
        self.assertIn("UNIQUE (action_code)", self.sql_content)

    def test_business_access_status_columns_have_check_constraints(self) -> None:
        """授权状态、动作状态和调用方法都由数据库 CHECK 约束限制取值。"""

        for constraint_name in (
            "ck_process_binding_status",
            "ck_business_action_binding_status",
            "ck_business_action_status",
            "ck_business_action_http_method",
        ):
            self.assertIn(constraint_name, self.sql_content)

    def test_business_access_tables_do_not_reference_other_schemas(self) -> None:
        """跨 Schema 的业务资源 ID 不建立外键，tenant Schema 可以独立移除。"""

        # 授权和使用记录表只允许对 tenant.tenant 建立外键。
        for table_name, foreign_key_name in (
            ("tenant.process_binding", "fk_process_binding_tenant"),
            (
                "tenant.business_action_binding",
                "fk_business_action_binding_tenant",
            ),
            ("tenant.process_usage_record", "fk_process_usage_record_tenant"),
        ):
            table_start = self.sql_content.index(
                f"CREATE TABLE IF NOT EXISTS {table_name}"
            )
            table_end = self.sql_content.index(";", table_start)
            table_definition = self.sql_content[table_start:table_end]
            self.assertIn(foreign_key_name, table_definition)
            self.assertNotIn("REFERENCES process.", table_definition)
            self.assertNotIn("REFERENCES integration.", table_definition)

    def test_business_action_relative_path_has_safety_check(self) -> None:
        """相对路径由数据库兜底拒绝完整 URL 和协议相对地址。"""

        self.assertIn("ck_business_action_relative_path", self.sql_content)
        self.assertIn("relative_path NOT LIKE '%://%'", self.sql_content)

    def test_business_execution_table_is_declared(self) -> None:
        """业务执行表和它自己的字段都带注释，结构由数据库约束兜底。"""

        self.assertIn(
            "CREATE TABLE IF NOT EXISTS process.business_execution_record",
            self.sql_content,
        )

        table_start = self.sql_content.index(
            "CREATE TABLE IF NOT EXISTS process.business_execution_record"
        )
        table_end = self.sql_content.index(";", table_start)
        table_definition = self.sql_content[table_start:table_end]

        # 同一个审批实例最多产生一条执行记录，唯一约束是防止重复执行的最终保障。
        self.assertIn("uq_business_execution_record_instance", table_definition)
        self.assertIn("UNIQUE (approval_instance_id)", table_definition)
        self.assertIn("ck_business_execution_record_status", table_definition)
        for status_value in ("PENDING", "RUNNING", "SUCCEEDED", "FAILED"):
            self.assertIn(f"'{status_value}'", table_definition)

        # 跨 Schema 的业务动作 ID 不建立外键，但审批实例同属 process Schema，可以建立外键。
        self.assertIn("REFERENCES process.approval_instance (id)", table_definition)
        self.assertNotIn("REFERENCES integration.", table_definition)
        self.assertNotIn("tenant_id", table_definition)

        self.assertIn(
            "COMMENT ON TABLE process.business_execution_record IS",
            self.sql_content,
        )
        for column_name in (
            "id",
            "approval_instance_id",
            "business_action_id",
            "action_code",
            "request_url",
            "http_method",
            "relative_path",
            "success_status_codes_json",
            "timeout_ms",
            "request_payload_json",
            "status",
            "http_status_code",
            "response_body",
            "error_message",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
        ):
            self.assertIn(
                f"COMMENT ON COLUMN process.business_execution_record.{column_name} IS",
                self.sql_content,
            )

    def test_execution_table_does_not_store_duration(self) -> None:
        """耗时由时间字段相减得到，不重复保存 duration_ms。"""

        table_start = self.sql_content.index(
            "CREATE TABLE IF NOT EXISTS process.business_execution_record"
        )
        table_end = self.sql_content.index(";", table_start)
        table_definition = self.sql_content[table_start:table_end]

        self.assertNotIn("duration_ms", table_definition)

    def test_callback_credential_uses_service_token_structure(self) -> None:
        """回调凭据表保存 Service Token，一个租户最多一条 ACTIVE 记录。"""

        table_start = self.sql_content.index(
            "CREATE TABLE IF NOT EXISTS tenant.tenant_callback_credential"
        )
        table_end = self.sql_content.index(";", table_start)
        table_definition = self.sql_content[table_start:table_end]

        self.assertIn("header_name VARCHAR(100) NOT NULL", table_definition)
        self.assertIn("token_prefix VARCHAR(50) NOT NULL", table_definition)
        self.assertIn("token_ciphertext TEXT NOT NULL", table_definition)
        self.assertIn("ck_tenant_callback_credential_status", table_definition)
        self.assertIn("CHECK (status IN ('ACTIVE', 'REVOKED'))", table_definition)
        # 早期 HMAC 结构的列不再出现。
        self.assertNotIn("key_id", table_definition)
        self.assertNotIn("secret_ciphertext", table_definition)

        self.assertIn(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_tenant_callback_credential_one_active",
            self.sql_content,
        )
        self.assertIn("WHERE status = 'ACTIVE'", self.sql_content)

        for column_name in (
            "header_name",
            "token_prefix",
            "token_ciphertext",
        ):
            self.assertIn(
                f"COMMENT ON COLUMN tenant.tenant_callback_credential.{column_name} IS",
                self.sql_content,
            )

    def test_callback_credential_upgrade_script_has_data_guard(self) -> None:
        """凭据升级脚本必须在存在 ACTIVE 凭据时主动中止。"""

        migration_path = (
            INITIALIZATION_SQL_PATH.parent
            / "migrations"
            / "20260922_callback_credential_service_token.sql"
        )
        migration_content = migration_path.read_text(encoding="utf-8")

        self.assertIn(
            "IF EXISTS (\n        SELECT 1 FROM tenant.tenant_callback_credential "
            "WHERE status = 'ACTIVE'\n    )",
            migration_content,
        )
        self.assertIn("RAISE EXCEPTION", migration_content)
        self.assertIn("DROP COLUMN IF EXISTS key_id", migration_content)
        self.assertIn("DROP COLUMN IF EXISTS secret_ciphertext", migration_content)

    def test_seed_node_definitions_are_complete(self) -> None:
        """seed 注册了 START、APPROVAL、CONDITION、END 四种节点能力。"""

        definitions = load_seed_node_definitions()
        self.assertEqual(set(definitions), {"START", "APPROVAL", "CONDITION", "END"})

        expected_ids = {
            "START": "00000000-0000-0000-0000-000000000101",
            "APPROVAL": "00000000-0000-0000-0000-000000000102",
            "END": "00000000-0000-0000-0000-000000000103",
            "CONDITION": "00000000-0000-0000-0000-000000000104",
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
        """审批节点声明了必填项；结束节点没有配置项。"""

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

        # 结束节点走到就是审批通过、流程完成，没有可配置项，也就没有必填项。
        end_schema = definitions["END"].config_schema_json
        self.assertEqual(end_schema["properties"], {})
        self.assertNotIn("required", end_schema)


if __name__ == "__main__":
    unittest.main()
