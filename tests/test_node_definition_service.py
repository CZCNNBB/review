"""节点能力定义服务层测试，需要可用的 PostgreSQL 数据库。"""

import unittest
from uuid import uuid4

from pydantic import ValidationError
from sqlmodel import Session

from tests.process_test_helpers import DatabaseTestCaseMixin
from app.server.process.src.models.process_model import (
    ApprovalProcess,
    ApprovalProcessNode,
)
from app.server.process.src.schemas.node_definition_schema import (
    NodeDefinitionCreateRequest,
    NodeDefinitionUpdateRequest,
)
from app.server.process.src.service.exceptions import (
    NodeDefinitionNotFoundError,
    ProcessConflictError,
)
from app.server.process.src.service.node_definition_service import (
    NodeDefinitionService,
)


def unique_name(prefix: str) -> str:
    """生成不与其他测试冲突的节点定义名称。"""

    return f"{prefix}-{uuid4().hex[:8]}"


class NodeDefinitionServiceTestCase(DatabaseTestCaseMixin, unittest.TestCase):
    """验证节点能力定义的增删改查和校验。"""

    def setUp(self) -> None:
        """准备数据库会话和服务。"""

        self.db: Session = self.open_session()
        self.service = NodeDefinitionService()

    def tearDown(self) -> None:
        """清理测试创建的节点定义并关闭会话。"""

        self.close_session()

    def create_definition(self, **overrides):
        """创建一个测试节点定义并登记清理。"""

        payload = {
            "node_type": "APPROVAL",
            "name": unique_name("测试审批节点"),
            "description": "用于测试的节点定义",
            "icon": "user-check",
            "config_schema_json": {
                "type": "object",
                "required": ["approval_mode"],
                "properties": {"approval_mode": {"type": "string"}},
            },
        }
        payload.update(overrides)
        definition = self.service.create_definition(
            NodeDefinitionCreateRequest(**payload),
            self.db,
        )
        self.track_node_definition(definition.id)
        return definition

    def reference_from_enabled_process(self, definition_id):
        """创建一条已启用流程，让其节点实例引用指定节点定义。"""

        process = ApprovalProcess(
            name=unique_name("引用节点定义的流程"),
            status="ENABLED",
        )
        self.db.add(process)
        self.db.flush()
        self.db.add(
            ApprovalProcessNode(
                id=uuid4(),
                process_id=process.id,
                node_definition_id=definition_id,
                name="被引用节点",
                config_json={},
                position_json={},
            )
        )
        self.db.commit()
        self.track_process(process.id)
        return process

    def test_create_and_get_definition(self) -> None:
        """创建后可以按主键查询。"""

        definition = self.create_definition()
        loaded = self.service.get_definition(definition.id, self.db)
        self.assertEqual(loaded.name, definition.name)
        self.assertEqual(loaded.node_type, "APPROVAL")
        self.assertEqual(loaded.status, "ENABLED")

    def test_duplicate_name_is_rejected(self) -> None:
        """节点定义名称重复时返回领域冲突。"""

        definition = self.create_definition()
        with self.assertRaises(ProcessConflictError):
            self.service.create_definition(
                NodeDefinitionCreateRequest(
                    node_type="APPROVAL",
                    name=definition.name,
                ),
                self.db,
            )

    def test_get_missing_definition_raises(self) -> None:
        """查询不存在的节点定义时抛出领域异常。"""

        with self.assertRaises(NodeDefinitionNotFoundError):
            self.service.get_definition(uuid4(), self.db)

    def test_list_definitions_can_be_paginated(self) -> None:
        """列表支持分页，且包含测试创建的节点定义。"""

        definition = self.create_definition()
        listed_ids = {
            item.id for item in self.service.list_definitions(self.db, offset=0, limit=500)
        }
        self.assertIn(definition.id, listed_ids)

    def test_invalid_config_schema_is_rejected(self) -> None:
        """配置 Schema 本身非法时在请求层被拒绝。"""

        with self.assertRaises(ValidationError):
            NodeDefinitionCreateRequest(
                node_type="APPROVAL",
                name=unique_name("非法Schema节点"),
                config_schema_json={"type": "unknown-type"},
            )

    def test_non_object_config_schema_is_rejected(self) -> None:
        """配置 Schema 根类型必须是对象。"""

        with self.assertRaises(ValidationError):
            NodeDefinitionCreateRequest(
                node_type="APPROVAL",
                name=unique_name("根类型错误节点"),
                config_schema_json={"type": "array"},
            )

    def test_config_schema_without_root_type_is_rejected(self) -> None:
        """非空配置 Schema 必须显式声明根类型为 object。"""

        with self.assertRaises(ValidationError):
            NodeDefinitionCreateRequest(
                node_type="APPROVAL",
                name=unique_name("缺少根类型节点"),
                config_schema_json={
                    "properties": {"approval_mode": {"type": "string"}}
                },
            )

    def test_unsupported_node_type_is_rejected(self) -> None:
        """node_type 必须落在后端支持的类型集合内。"""

        with self.assertRaises(ValidationError):
            NodeDefinitionCreateRequest(
                node_type="BRANCH",
                name=unique_name("分支节点"),
            )

    def test_update_changes_name_and_status(self) -> None:
        """更新接口可以改名称和启停状态。"""

        definition = self.create_definition()
        new_name = unique_name("改名节点")
        updated = self.service.update_definition(
            definition.id,
            NodeDefinitionUpdateRequest(name=new_name, status="DISABLED"),
            self.db,
        )
        self.assertEqual(updated.name, new_name)
        self.assertEqual(updated.status, "DISABLED")

    def test_update_to_existing_name_is_rejected(self) -> None:
        """改成一个已存在的名称时返回领域冲突。"""

        first = self.create_definition()
        second = self.create_definition()
        with self.assertRaises(ProcessConflictError):
            self.service.update_definition(
                second.id,
                NodeDefinitionUpdateRequest(name=first.name),
                self.db,
            )

    def test_update_rejects_empty_payload(self) -> None:
        """更新请求必须至少提供一个字段。"""

        with self.assertRaises(ValidationError):
            NodeDefinitionUpdateRequest()

    def test_node_type_cannot_be_changed(self) -> None:
        """更新请求不接收 node_type，传入也不会生效。"""

        definition = self.create_definition()
        request = NodeDefinitionUpdateRequest.model_validate(
            {"node_type": "END", "icon": "flag"}
        )
        updated = self.service.update_definition(definition.id, request, self.db)
        self.assertEqual(updated.node_type, "APPROVAL")
        self.assertEqual(updated.icon, "flag")

    def test_enabled_process_reference_blocks_disabling_definition(self) -> None:
        """节点定义被已启用流程引用时不允许停用。"""

        definition = self.create_definition()
        self.reference_from_enabled_process(definition.id)

        with self.assertRaises(ProcessConflictError):
            self.service.update_definition(
                definition.id,
                NodeDefinitionUpdateRequest(status="DISABLED"),
                self.db,
            )

        self.assertEqual(self.service.get_definition(definition.id, self.db).status, "ENABLED")

    def test_enabled_process_reference_blocks_config_schema_change(self) -> None:
        """节点定义被已启用流程引用时不允许改变配置契约。"""

        definition = self.create_definition()
        self.reference_from_enabled_process(definition.id)

        with self.assertRaises(ProcessConflictError):
            self.service.update_definition(
                definition.id,
                NodeDefinitionUpdateRequest(
                    config_schema_json={
                        "type": "object",
                        "required": ["approval_mode", "reason"],
                        "properties": {
                            "approval_mode": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                    }
                ),
                self.db,
            )

        reloaded = self.service.get_definition(definition.id, self.db)
        self.assertNotIn("reason", reloaded.config_schema_json.get("required", []))


if __name__ == "__main__":
    unittest.main()
