"""节点定义同步测试：代码清单落到数据库行的行为。

节点类型跟着代码走，``process.node_definition`` 是代码清单的副本，启动时同步。这里
验证同步的几条约定：认清单里的固定 id（不换 id、认准那一行）、把手工改动改回来、
代码里没有的类型停用但不删除、重复同步不产生重复行。

挑选正主与写库是分开的两段：挑选是纯函数，不需要数据库；其余用例连库跑。
"""

import unittest
from uuid import uuid4

from sqlmodel import Session

from tests.process_test_helpers import (
    DatabaseTestCaseMixin,
    load_builtin_node_definitions,
)
from app.server.process.src.constants import (
    NODE_DEFINITION_STATUS_DISABLED,
    NODE_DEFINITION_STATUS_ENABLED,
)
from app.server.process.src.models.process_model import NodeDefinition
from app.server.process.src.node_catalog import NODE_TYPES
from app.server.process.src.repository.node_definition_repository import (
    NodeDefinitionRepository,
)
from app.server.process.src.service.node_definition_sync import (
    pick_definition_rows,
    sync_node_definitions,
)

# 代码里没有的节点类型，用来验证"停用而不是删除"
RETIRED_NODE_TYPE = "HTTP_CALL"


def unique_name(prefix: str) -> str:
    """生成不与其他测试冲突的节点定义名称。"""

    return f"{prefix}-{uuid4().hex[:8]}"


def make_row(node_type: str, name: str = "测试行") -> NodeDefinition:
    """造一个未入库的定义行，只用于挑选逻辑。"""

    return NodeDefinition(id=uuid4(), node_type=node_type, name=name)


class PickDefinitionRowsTestCase(unittest.TestCase):
    """挑选正主的逻辑不碰数据库，单独测。

    这段是同步里最容易出错的地方，而"库里一行都没有"（全新库第一次启动）在开发库上
    根本走不到 —— open_session 已经同步过了，所以只能这样覆盖。
    """

    def setUp(self) -> None:
        """用审批类型的清单条目当被测对象。"""

        self.node_type = "APPROVAL"
        self.spec = NODE_TYPES[self.node_type]

    def test_creates_row_with_catalog_id_when_table_is_empty(self) -> None:
        """全新库：按清单里的固定 id 造一个新行，没有多余行要停用。"""

        primary, extras = pick_definition_rows(self.node_type, self.spec, [])

        self.assertEqual(primary.id, self.spec.id)
        self.assertEqual(primary.node_type, self.node_type)
        self.assertEqual(extras, [])

    def test_keeps_existing_id_when_catalog_row_is_absent(self) -> None:
        """库里只有手工建的行：沿用它的 id —— 版本节点可能引用着它。"""

        existing = make_row(self.node_type)

        primary, extras = pick_definition_rows(self.node_type, self.spec, [existing])

        self.assertIs(primary, existing)
        self.assertEqual(extras, [])

    def test_catalog_row_wins_whatever_the_order(self) -> None:
        """清单那一行才是正主，与它在列表里的位置无关；多出来的行都要停用。"""

        catalog_row = make_row(self.node_type, "清单那一行")
        catalog_row.id = self.spec.id
        extra = make_row(self.node_type, "手工多建的")

        for rows in ([catalog_row, extra], [extra, catalog_row]):
            primary, extras = pick_definition_rows(self.node_type, self.spec, rows)
            self.assertIs(primary, catalog_row)
            self.assertEqual(extras, [extra])


class NodeDefinitionSyncTestCase(DatabaseTestCaseMixin, unittest.TestCase):
    """验证启动同步把代码清单写进节点定义表。"""

    def setUp(self) -> None:
        """准备数据库会话；open_session 里的同步就是应用启动时那一次。"""

        self.db: Session = self.open_session()
        self.repository = NodeDefinitionRepository()
        self.definitions = load_builtin_node_definitions()

    def tearDown(self) -> None:
        """清理测试创建的节点定义并关闭会话。"""

        self.close_session()

    def enabled_definition(self, node_type: str) -> NodeDefinition | None:
        """取某种类型当前启用中的定义行。"""

        definitions = self.repository.list_definitions(self.db, offset=0, limit=1000)
        for definition in definitions:
            if definition.node_type != node_type:
                continue
            if definition.status == NODE_DEFINITION_STATUS_ENABLED:
                return definition
        return None

    def test_sync_creates_builtin_rows_with_catalog_ids(self) -> None:
        """每种内置类型都有且只有一条启用中的定义行，id 与清单里定下的一致。"""

        for node_type, spec in self.definitions.items():
            definition = self.enabled_definition(node_type)
            self.assertIsNotNone(definition, node_type)
            self.assertEqual(definition.id, spec.id, node_type)
            self.assertEqual(definition.name, spec.name, node_type)
            self.assertEqual(definition.icon, spec.icon, node_type)
            self.assertEqual(
                definition.config_schema_json,
                spec.config_schema_json,
                node_type,
            )

    def test_sync_keeps_existing_id_and_repairs_manual_edits(self) -> None:
        """既有行按 node_type 认，保留自己的 id；改坏的元数据被改回清单内容。"""

        definition = self.enabled_definition("APPROVAL")
        self.assertIsNotNone(definition)
        definition.description = "被人手工改过的说明"
        definition.icon = "hand-edited"
        self.db.add(definition)
        self.db.commit()

        sync_node_definitions(self.db)

        repaired = self.enabled_definition("APPROVAL")
        self.assertEqual(repaired.id, definition.id)
        self.assertEqual(repaired.description, self.definitions["APPROVAL"].description)
        self.assertEqual(repaired.icon, self.definitions["APPROVAL"].icon)

    def test_sync_disables_extra_rows_of_a_builtin_type(self) -> None:
        """同一类型多出来的行被停用：正主永远是清单里那一行，一类只留一种形态。"""

        extra = NodeDefinition(
            node_type="APPROVAL",
            name=unique_name("测试多建的一个审批节点"),
            description="手工建的第二个审批类型定义，用来验证同步会把它停用",
            config_schema_json={"type": "object", "properties": {}},
            ui_schema_json={},
        )
        self.db.add(extra)
        self.db.commit()
        self.db.refresh(extra)
        self.track_node_definition(extra.id)

        sync_node_definitions(self.db)

        self.db.refresh(extra)
        self.assertEqual(extra.status, NODE_DEFINITION_STATUS_DISABLED)
        kept = self.enabled_definition("APPROVAL")
        self.assertEqual(kept.id, self.definitions["APPROVAL"].id)

    def test_sync_disables_types_missing_from_catalog(self) -> None:
        """代码里已经没有的类型被停用，行本身保留 —— 历史版本的节点还引用着它。"""

        retired = NodeDefinition(
            node_type=RETIRED_NODE_TYPE,
            name=unique_name("测试已下线的节点"),
            description="代码里没有这个类型，用来验证同步只停用不删除",
            config_schema_json={"type": "object", "properties": {}},
            ui_schema_json={},
        )
        self.db.add(retired)
        self.db.commit()
        self.db.refresh(retired)
        self.track_node_definition(retired.id)

        sync_node_definitions(self.db)

        self.db.refresh(retired)
        self.assertEqual(retired.status, NODE_DEFINITION_STATUS_DISABLED)
        self.assertEqual(retired.node_type, RETIRED_NODE_TYPE)

    def test_sync_is_repeatable(self) -> None:
        """重复同步不会产生重复行，启用中的内置定义仍是一类一条。"""

        sync_node_definitions(self.db)
        sync_node_definitions(self.db)

        definitions = self.repository.list_definitions(self.db, offset=0, limit=1000)
        enabled_by_type = {}
        for definition in definitions:
            if definition.status == NODE_DEFINITION_STATUS_ENABLED:
                enabled_by_type.setdefault(definition.node_type, []).append(definition)

        for node_type in self.definitions:
            self.assertEqual(len(enabled_by_type.get(node_type, [])), 1, node_type)
