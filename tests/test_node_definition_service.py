"""节点能力定义查询测试，需要可用的 PostgreSQL 数据库。

接口是只读的：节点定义由代码清单在启动时同步写入（见 test_node_definition_sync），
这里只管查询本身 —— 取不存在的 id 报领域异常、分页、列表顺序。
"""

import unittest
from uuid import uuid4

from sqlmodel import Session

from tests.process_test_helpers import (
    DatabaseTestCaseMixin,
    load_builtin_node_definitions,
)
from app.server.process.src.service.exceptions import NodeDefinitionNotFoundError
from app.server.process.src.service.node_definition_service import (
    NodeDefinitionService,
)


class NodeDefinitionServiceTestCase(DatabaseTestCaseMixin, unittest.TestCase):
    """验证节点能力定义的查询。"""

    def setUp(self) -> None:
        """准备数据库会话和服务。"""

        self.db: Session = self.open_session()
        self.service = NodeDefinitionService()
        self.definitions = load_builtin_node_definitions()

    def tearDown(self) -> None:
        """关闭会话。"""

        self.close_session()

    def test_get_definition_returns_builtin_row(self) -> None:
        """按主键能取到内置定义，字段与代码清单一致。"""

        spec = self.definitions["APPROVAL"]
        loaded = self.service.get_definition(spec.id, self.db)

        self.assertEqual(loaded.node_type, "APPROVAL")
        self.assertEqual(loaded.name, spec.name)
        self.assertEqual(loaded.config_schema_json, spec.config_schema_json)

    def test_get_missing_definition_raises(self) -> None:
        """查询不存在的节点定义时抛出领域异常。"""

        with self.assertRaises(NodeDefinitionNotFoundError):
            self.service.get_definition(uuid4(), self.db)

    def test_list_definitions_can_be_paginated(self) -> None:
        """列表按 offset/limit 分页，且包含全部内置定义。"""

        listed_ids = {
            item.id for item in self.service.list_definitions(self.db, offset=0, limit=500)
        }
        self.assertTrue({spec.id for spec in self.definitions.values()} <= listed_ids)

        first_page = self.service.list_definitions(self.db, offset=0, limit=1)
        self.assertEqual(len(first_page), 1)

    def test_list_definitions_follows_catalog_order(self) -> None:
        """列表按代码清单的顺序返回，画布的节点面板和「节点定义」页都读这个顺序。"""

        builtin_ids = [
            definition.id for definition in load_builtin_node_definitions().values()
        ]
        listed_ids = [
            item.id for item in self.service.list_definitions(self.db, offset=0, limit=500)
        ]
        positions = [listed_ids.index(node_definition_id) for node_definition_id in builtin_ids]
        self.assertEqual(positions, sorted(positions))


if __name__ == "__main__":
    unittest.main()
