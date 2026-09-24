"""节点类型清单：清单、白名单与处理器注册表必须始终对得上。

清单在 src/node_catalog.py，处理器在 engine/nodes/registry.py。两边分开是有意的
（声明与执行分离，也避免 import 成环），所以用测试把"它们指向同一批类型"钉住 ——
registry 在 import 时也会断言一次，这里再从几个角度确认一遍。
"""

import unittest

from app.server.process.src.constants import (
    NODE_TYPE_APPROVAL,
    NODE_TYPE_CONDITION,
    NODE_TYPE_END,
    NODE_TYPE_START,
)
from app.server.process.src.engine.nodes import NODE_HANDLERS
from app.server.process.src.node_catalog import (
    NODE_TYPES,
    SUPPORTED_NODE_TYPES,
)


class NodeCatalogTestCase(unittest.TestCase):
    def test_catalog_holds_the_builtin_types(self) -> None:
        """内置四种节点类型都在清单里，一种不多一种不少。"""

        self.assertEqual(
            set(NODE_TYPES),
            {NODE_TYPE_START, NODE_TYPE_APPROVAL, NODE_TYPE_CONDITION, NODE_TYPE_END},
        )

    def test_whitelist_is_derived_from_catalog(self) -> None:
        """白名单由清单派生（流程校验读它），加类型不会漏改第二处。"""

        self.assertEqual(SUPPORTED_NODE_TYPES, frozenset(NODE_TYPES))
        # 代码里没实现的类型必须落在白名单外
        self.assertNotIn("HTTP_CALL", SUPPORTED_NODE_TYPES)

    def test_every_type_has_a_handler(self) -> None:
        """每种类型都有处理器，且处理器实现了 handle。"""

        self.assertEqual(set(NODE_HANDLERS), set(NODE_TYPES))
        for node_type, handler in NODE_HANDLERS.items():
            self.assertTrue(callable(handler.handle), node_type)

    def test_spec_carries_what_the_console_needs(self) -> None:
        """名字、图标与配置 Schema 齐全：画布、配置弹窗与节点定义行都读这些。"""

        for node_type, spec in NODE_TYPES.items():
            self.assertTrue(spec.name, node_type)
            self.assertTrue(spec.icon, node_type)
            # 配置弹窗按 Schema 生成表单，根类型必须是 object
            self.assertEqual(spec.config_schema_json.get("type"), "object", node_type)

    def test_builtin_definition_ids_are_fixed_and_unique(self) -> None:
        """内置类型的固定 id 是既有库里那一行的身份，不能随手改。"""

        self.assertEqual(
            {node_type: str(spec.id) for node_type, spec in NODE_TYPES.items()},
            {
                NODE_TYPE_START: "00000000-0000-0000-0000-000000000101",
                NODE_TYPE_APPROVAL: "00000000-0000-0000-0000-000000000102",
                NODE_TYPE_END: "00000000-0000-0000-0000-000000000103",
                NODE_TYPE_CONDITION: "00000000-0000-0000-0000-000000000104",
            },
        )
        self.assertEqual(len({spec.id for spec in NODE_TYPES.values()}), len(NODE_TYPES))

    def test_config_schemas_declare_required_config(self) -> None:
        """审批节点的必填项与枚举、结束节点的无配置项，都是引擎和画布依赖的契约。"""

        approval_schema = NODE_TYPES[NODE_TYPE_APPROVAL].config_schema_json
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
        end_schema = NODE_TYPES[NODE_TYPE_END].config_schema_json
        self.assertEqual(end_schema["properties"], {})
        self.assertNotIn("required", end_schema)
