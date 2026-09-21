"""审批流完整性校验引擎单元测试。

本文件只测试纯函数，不需要数据库连接。节点定义直接使用 init.sql 里注册的
seed 配置 Schema，保证测试对象和生产环境完全一致。
"""

import unittest
from dataclasses import replace
from uuid import UUID, uuid4

from tests.process_test_helpers import load_seed_node_definitions
from app.server.process.src.constants import (
    RULE_APPROVAL_MODE_INVALID,
    RULE_APPROVER_DISABLED,
    RULE_APPROVER_DUPLICATE,
    RULE_APPROVER_ID_INVALID,
    RULE_APPROVER_NOT_FOUND,
    RULE_APPROVER_REQUIRED,
    RULE_CONNECTION_CONDITION_INVALID,
    RULE_CONNECTION_CONDITION_REQUIRED,
    RULE_CONNECTION_DEFAULT_REQUIRED,
    RULE_CONNECTION_DEFAULT_DUPLICATE,
    RULE_CONNECTION_DEFAULT_WITH_CONDITION,
    RULE_CONNECTION_FIELD_UNKNOWN,
    RULE_CONNECTION_NODE_UNKNOWN,
    RULE_CONNECTION_OPERATOR_INCOMPATIBLE,
    RULE_CONNECTION_VALUE_NOT_IN_ENUM,
    RULE_END_APPROVED_REQUIRED,
    RULE_END_AS_SOURCE,
    RULE_END_REQUIRED,
    RULE_END_RESULT_STATUS_INVALID,
    RULE_GRAPH_CYCLE,
    RULE_NODE_CONFIG_INVALID,
    RULE_NODE_DEFINITION_DISABLED,
    RULE_NODE_DEFINITION_NOT_FOUND,
    RULE_NODE_UNREACHABLE,
    RULE_NODE_WITHOUT_OUTGOING,
    RULE_ORCHESTRATION_INVALID,
    RULE_START_AS_TARGET,
    RULE_START_COUNT_INVALID,
)
from app.server.process.src.service.exceptions import ProcessValidationError
from app.server.process.src.service.process_validation import (
    build_graph,
    collect_form_fields,
    parse_connections,
    remap_orchestration,
    validate_graph,
)


# 测试使用的审批表单，覆盖数字、字符串、枚举、日期、布尔和无类型字段。
FORM_SCHEMA = {
    "type": "object",
    "properties": {
        "amount": {"type": "number", "title": "付款金额"},
        "reason": {"type": "string", "title": "事由"},
        "level": {"type": "string", "enum": ["NORMAL", "URGENT"]},
        "submit_date": {"type": "string", "format": "date"},
        "flag": {"type": "boolean"},
        "payload": {
            "type": "object",
            "properties": {"nested_amount": {"type": "number"}},
        },
        "free_text": {},
    },
}


class ValidationTestCase(unittest.TestCase):
    """校验引擎测试基类，提供流程视图构造辅助。"""

    def setUp(self) -> None:
        """读取 seed 节点定义并准备默认审批人。"""

        self.seed = load_seed_node_definitions()
        self.definitions = {definition.id: definition for definition in self.seed.values()}
        self.person_id = uuid4()
        self.person_statuses = {self.person_id: "ENABLED"}

    def start_node(self, node_id: UUID | None = None) -> tuple:
        """构造开始节点输入。"""

        return (node_id or uuid4(), self.seed["START"].id, "开始", {})

    def approval_node(
        self,
        node_id: UUID | None = None,
        *,
        name: str = "财务审批",
        config: dict | None = None,
        person_ids: tuple[UUID, ...] | None = None,
        approval_mode: str = "AND",
    ) -> tuple:
        """构造人工审批节点输入。"""

        if config is None:
            approvers = person_ids if person_ids is not None else (self.person_id,)
            config = {
                "approval_mode": approval_mode,
                "approvers": [{"person_id": str(item)} for item in approvers],
            }
        return (node_id or uuid4(), self.seed["APPROVAL"].id, name, config)

    def end_node(
        self,
        node_id: UUID | None = None,
        *,
        result_status: str = "APPROVED",
        name: str = "结束",
    ) -> tuple:
        """构造结束节点输入。"""

        return (
            node_id or uuid4(),
            self.seed["END"].id,
            name,
            {"result_status": result_status},
        )

    def connection(
        self,
        source_node_id: UUID,
        target_node_id: UUID,
        condition: dict | None = None,
        is_default: bool = False,
    ) -> dict:
        """构造一条编排连线。"""

        raw_connection: dict = {
            "source_node_id": str(source_node_id),
            "target_node_id": str(target_node_id),
        }
        if condition is not None:
            raw_connection["condition"] = condition
        if is_default:
            raw_connection["default"] = True
        return raw_connection

    def validate(
        self,
        nodes: list[tuple],
        connections: list[dict],
        *,
        definitions: dict | None = None,
        person_statuses: dict | None = None,
        form_schema: dict | None = None,
    ) -> list:
        """组装流程视图并执行完整校验，返回问题列表。"""

        graph, issues = build_graph(
            nodes,
            FORM_SCHEMA if form_schema is None else form_schema,
            {"connections": connections},
        )
        issues.extend(
            validate_graph(
                graph,
                definitions=self.definitions if definitions is None else definitions,
                person_statuses=(
                    self.person_statuses if person_statuses is None else person_statuses
                ),
            )
        )
        return issues

    @staticmethod
    def codes(issues: list) -> list[str]:
        """取出问题列表中的规则码。"""

        return [issue.code for issue in issues]

    def assert_has_code(self, issues: list, expected_code: str) -> None:
        """断言问题列表包含指定规则码。"""

        self.assertIn(
            expected_code,
            self.codes(issues),
            f"期望包含规则 {expected_code}，实际为 {self.codes(issues)}",
        )


class ValidGraphTestCase(ValidationTestCase):
    """合法流程不应产生任何问题。"""

    def test_minimal_process_is_valid(self) -> None:
        """开始到审批再到通过的结束节点是合法流程。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [self.connection(start, approval), self.connection(approval, end)],
        )
        self.assertEqual(issues, [])

    def test_conditional_branch_with_default_is_valid(self) -> None:
        """条件分支加默认路径是合法编排。"""

        start, approval, manager, end = uuid4(), uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [
                self.start_node(start),
                self.approval_node(approval),
                self.approval_node(manager, name="负责人审批"),
                self.end_node(end),
            ],
            [
                self.connection(start, approval),
                self.connection(
                    approval,
                    manager,
                    condition={
                        "field": "approval_form.amount",
                        "operator": "GT",
                        "value": 10000,
                    },
                ),
                self.connection(approval, end, is_default=True),
                self.connection(manager, end),
            ],
        )
        self.assertEqual(issues, [])

    def test_single_conditional_connection_requires_default(self) -> None:
        """即使只有一条条件连线，也必须提供条件不命中时的默认路径。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [
                self.connection(start, approval),
                self.connection(
                    approval,
                    end,
                    condition={
                        "field": "approval_form.level",
                        "operator": "EQ",
                        "value": "URGENT",
                    },
                ),
            ],
        )
        self.assert_has_code(issues, RULE_CONNECTION_DEFAULT_REQUIRED)

    def test_nested_form_field_path_is_supported(self) -> None:
        """嵌套表单字段路径可以用于条件。"""

        start, approval, end, fallback_end = uuid4(), uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [
                self.start_node(start),
                self.approval_node(approval),
                self.end_node(end),
                self.end_node(
                    fallback_end,
                    result_status="REJECTED",
                    name="默认结束",
                ),
            ],
            [
                self.connection(start, approval),
                self.connection(
                    approval,
                    end,
                    condition={
                        "field": "approval_form.payload.nested_amount",
                        "operator": "GTE",
                        "value": 1,
                    },
                ),
                self.connection(approval, fallback_end, is_default=True),
            ],
        )
        self.assertEqual(issues, [])


class NodeDefinitionRuleTestCase(ValidationTestCase):
    """节点定义引用规则。"""

    def test_missing_definition_is_reported(self) -> None:
        """引用不存在的节点定义时报出规则码。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        nodes = [
            self.start_node(start),
            (approval, uuid4(), "财务审批", {"approval_mode": "AND", "approvers": []}),
            self.end_node(end),
        ]
        definitions = {
            self.seed["START"].id: self.seed["START"],
            self.seed["END"].id: self.seed["END"],
        }
        issues = self.validate(
            nodes,
            [self.connection(start, approval), self.connection(approval, end)],
            definitions=definitions,
        )
        self.assert_has_code(issues, RULE_NODE_DEFINITION_NOT_FOUND)

    def test_disabled_definition_is_reported(self) -> None:
        """引用已停用的节点定义时报出规则码。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        definitions = dict(self.definitions)
        definitions[self.seed["APPROVAL"].id] = replace(
            self.seed["APPROVAL"],
            status="DISABLED",
        )
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [self.connection(start, approval), self.connection(approval, end)],
            definitions=definitions,
        )
        self.assert_has_code(issues, RULE_NODE_DEFINITION_DISABLED)


class NodeConfigRuleTestCase(ValidationTestCase):
    """节点配置结构校验。"""

    def test_missing_required_config_is_reported(self) -> None:
        """缺少必填配置项时给出中文提示和字段路径。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [
                self.start_node(start),
                self.approval_node(approval, config={"approval_mode": "AND"}),
                self.end_node(end),
            ],
            [self.connection(start, approval), self.connection(approval, end)],
        )
        config_issues = [
            issue for issue in issues if issue.code == RULE_NODE_CONFIG_INVALID
        ]
        self.assertTrue(config_issues)
        self.assertIn("缺少必填配置项 approvers", config_issues[0].message)
        self.assertIn("财务审批", config_issues[0].message)

    def test_enum_violation_is_reported(self) -> None:
        """审批模式取值超出枚举时报出中文提示。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [
                self.start_node(start),
                self.approval_node(
                    approval,
                    config={
                        "approval_mode": "XOR",
                        "approvers": [{"person_id": str(self.person_id)}],
                    },
                ),
                self.end_node(end),
            ],
            [self.connection(start, approval), self.connection(approval, end)],
        )
        config_messages = [
            issue.message
            for issue in issues
            if issue.code == RULE_NODE_CONFIG_INVALID
        ]
        self.assertTrue(any("AND、OR" in message for message in config_messages))

    def test_unexpected_config_field_is_reported(self) -> None:
        """节点配置出现 schema 未声明的字段时报出规则码。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [
                self.start_node(start),
                self.approval_node(
                    approval,
                    config={
                        "approval_mode": "AND",
                        "approvers": [{"person_id": str(self.person_id)}],
                        "extra_flag": True,
                    },
                ),
                self.end_node(end),
            ],
            [self.connection(start, approval), self.connection(approval, end)],
        )
        self.assert_has_code(issues, RULE_NODE_CONFIG_INVALID)


class ApproverRuleTestCase(ValidationTestCase):
    """审批人规则。"""

    def test_empty_approvers_is_reported(self) -> None:
        """审批人为空时报出规则码。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [
                self.start_node(start),
                self.approval_node(approval, person_ids=()),
                self.end_node(end),
            ],
            [self.connection(start, approval), self.connection(approval, end)],
        )
        self.assert_has_code(issues, RULE_APPROVER_REQUIRED)

    def test_invalid_mode_is_reported(self) -> None:
        """审批模式不是 AND 或 OR 时报出规则码。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [
                self.start_node(start),
                self.approval_node(approval, approval_mode="ALL"),
                self.end_node(end),
            ],
            [self.connection(start, approval), self.connection(approval, end)],
        )
        self.assert_has_code(issues, RULE_APPROVAL_MODE_INVALID)

    def test_malformed_person_id_is_reported(self) -> None:
        """审批人 ID 不是有效 UUID 时报出规则码。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [
                self.start_node(start),
                self.approval_node(
                    approval,
                    config={
                        "approval_mode": "AND",
                        "approvers": [{"person_id": "not-a-uuid"}],
                    },
                ),
                self.end_node(end),
            ],
            [self.connection(start, approval), self.connection(approval, end)],
        )
        self.assert_has_code(issues, RULE_APPROVER_ID_INVALID)

    def test_duplicate_approver_is_reported(self) -> None:
        """同一个审批人重复配置时报出规则码，不做静默去重。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [
                self.start_node(start),
                self.approval_node(approval, person_ids=(self.person_id, self.person_id)),
                self.end_node(end),
            ],
            [self.connection(start, approval), self.connection(approval, end)],
        )
        self.assert_has_code(issues, RULE_APPROVER_DUPLICATE)

    def test_unknown_approver_is_reported(self) -> None:
        """审批人不存在时报出规则码。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [self.connection(start, approval), self.connection(approval, end)],
            person_statuses={},
        )
        self.assert_has_code(issues, RULE_APPROVER_NOT_FOUND)

    def test_disabled_approver_is_reported(self) -> None:
        """审批人已停用时报出规则码。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [self.connection(start, approval), self.connection(approval, end)],
            person_statuses={self.person_id: "DISABLED"},
        )
        self.assert_has_code(issues, RULE_APPROVER_DISABLED)

    def test_approvers_are_not_checked_without_person_data(self) -> None:
        """不校验人员引用时仍会检查审批模式和审批人数量。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        graph, _ = build_graph(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            FORM_SCHEMA,
            {
                "connections": [
                    self.connection(start, approval),
                    self.connection(approval, end),
                ]
            },
        )
        issues = validate_graph(
            graph,
            definitions=self.definitions,
            person_statuses={},
            include_persons=False,
        )
        self.assertEqual(issues, [])


class StartEndRuleTestCase(ValidationTestCase):
    """开始节点和结束节点规则。"""

    def test_missing_start_is_reported(self) -> None:
        """没有开始节点时报出规则码。"""

        approval, end = uuid4(), uuid4()
        issues = self.validate(
            [self.approval_node(approval), self.end_node(end)],
            [self.connection(approval, end)],
        )
        self.assert_has_code(issues, RULE_START_COUNT_INVALID)

    def test_multiple_starts_are_reported(self) -> None:
        """存在多个开始节点时报出规则码。"""

        start_a, start_b, approval, end = uuid4(), uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [
                self.start_node(start_a),
                self.start_node(start_b),
                self.approval_node(approval),
                self.end_node(end),
            ],
            [
                self.connection(start_a, approval),
                self.connection(start_b, approval),
                self.connection(approval, end),
            ],
        )
        self.assert_has_code(issues, RULE_START_COUNT_INVALID)

    def test_missing_end_is_reported(self) -> None:
        """没有结束节点时报出规则码。"""

        start, approval = uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval)],
            [self.connection(start, approval)],
        )
        self.assert_has_code(issues, RULE_END_REQUIRED)

    def test_invalid_result_status_is_reported(self) -> None:
        """结束状态取值非法时报出规则码。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [
                self.start_node(start),
                self.approval_node(approval),
                self.end_node(end, result_status="MAYBE"),
            ],
            [self.connection(start, approval), self.connection(approval, end)],
        )
        self.assert_has_code(issues, RULE_END_RESULT_STATUS_INVALID)

    def test_flow_without_approved_end_is_rejected(self) -> None:
        """只有审批拒绝出口的流程没有任何成功路径。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [
                self.start_node(start),
                self.approval_node(approval),
                self.end_node(end, result_status="REJECTED"),
            ],
            [self.connection(start, approval), self.connection(approval, end)],
        )
        self.assert_has_code(issues, RULE_END_APPROVED_REQUIRED)


class ConnectionEndpointRuleTestCase(ValidationTestCase):
    """连线两端和连接方向规则。"""

    def test_start_as_target_is_reported(self) -> None:
        """开始节点不能作为连线目标。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [
                self.connection(start, approval),
                self.connection(approval, end),
                self.connection(approval, start),
            ],
        )
        self.assert_has_code(issues, RULE_START_AS_TARGET)

    def test_end_as_source_is_reported(self) -> None:
        """结束节点不能作为连线来源。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [
                self.connection(start, approval),
                self.connection(approval, end),
                self.connection(end, approval),
            ],
        )
        self.assert_has_code(issues, RULE_END_AS_SOURCE)

    def test_connection_to_foreign_node_is_reported(self) -> None:
        """连线引用了不属于当前流程的节点时报出规则码。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [
                self.connection(start, approval),
                self.connection(approval, end),
                self.connection(approval, uuid4()),
            ],
        )
        self.assert_has_code(issues, RULE_CONNECTION_NODE_UNKNOWN)


class TopologyRuleTestCase(ValidationTestCase):
    """可达性、出边和环的规则。"""

    def test_unreachable_node_is_reported(self) -> None:
        """孤立分支上的节点无法从开始节点到达。"""

        start, approval, end, orphan, orphan_end = (
            uuid4(),
            uuid4(),
            uuid4(),
            uuid4(),
            uuid4(),
        )
        issues = self.validate(
            [
                self.start_node(start),
                self.approval_node(approval),
                self.end_node(end),
                self.approval_node(orphan, name="孤立审批"),
                self.end_node(orphan_end, name="孤立结束"),
            ],
            [
                self.connection(start, approval),
                self.connection(approval, end),
                self.connection(orphan, orphan_end),
            ],
        )
        self.assert_has_code(issues, RULE_NODE_UNREACHABLE)

    def test_node_without_outgoing_connection_is_reported(self) -> None:
        """非结束节点没有后续连线时流程会中断。"""

        start, approval = uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval)],
            [self.connection(start, approval)],
        )
        self.assert_has_code(issues, RULE_NODE_WITHOUT_OUTGOING)

    def test_self_loop_is_reported(self) -> None:
        """节点指向自身的自环会被识别。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [
                self.connection(start, approval),
                self.connection(approval, end),
                self.connection(end, end),
            ],
        )
        self.assert_has_code(issues, RULE_GRAPH_CYCLE)
        cycle_messages = [
            issue.message for issue in issues if issue.code == RULE_GRAPH_CYCLE
        ]
        self.assertTrue(any("结束 → 结束" in message for message in cycle_messages))

    def test_two_node_cycle_is_reported(self) -> None:
        """两个节点互相指向形成的环会被识别。"""

        start, approval, manager, end = uuid4(), uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [
                self.start_node(start),
                self.approval_node(approval),
                self.approval_node(manager, name="负责人审批"),
                self.end_node(end),
            ],
            [
                self.connection(start, approval),
                self.connection(approval, manager),
                self.connection(manager, approval),
                self.connection(approval, end),
            ],
        )
        self.assert_has_code(issues, RULE_GRAPH_CYCLE)

    def test_three_node_cycle_is_reported(self) -> None:
        """三个节点首尾相接形成的环会被识别并输出完整路径。"""

        start, first, second, third = uuid4(), uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [
                self.start_node(start),
                self.approval_node(first, name="甲"),
                self.approval_node(second, name="乙"),
                self.approval_node(third, name="丙"),
            ],
            [
                self.connection(start, first),
                self.connection(first, second),
                self.connection(second, third),
                self.connection(third, first),
            ],
        )
        self.assert_has_code(issues, RULE_GRAPH_CYCLE)
        cycle_messages = [
            issue.message for issue in issues if issue.code == RULE_GRAPH_CYCLE
        ]
        self.assertTrue(any("甲 → 乙 → 丙 → 甲" in message for message in cycle_messages))

    def test_cycle_inside_unreachable_component_is_reported(self) -> None:
        """不可达分量里的环同样要报出来，不能只做一次可达遍历。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        orphan_a, orphan_b = uuid4(), uuid4()
        issues = self.validate(
            [
                self.start_node(start),
                self.approval_node(approval),
                self.end_node(end),
                self.approval_node(orphan_a, name="孤立甲"),
                self.approval_node(orphan_b, name="孤立乙"),
            ],
            [
                self.connection(start, approval),
                self.connection(approval, end),
                self.connection(orphan_a, orphan_b),
                self.connection(orphan_b, orphan_a),
            ],
        )
        self.assert_has_code(issues, RULE_GRAPH_CYCLE)
        cycle_messages = [
            issue.message for issue in issues if issue.code == RULE_GRAPH_CYCLE
        ]
        self.assertTrue(any("孤立甲 → 孤立乙 → 孤立甲" in message for message in cycle_messages))

    def test_start_count_error_suppresses_unreachable_noise(self) -> None:
        """开始节点数量异常时不再逐节点报不可达，避免刷屏。"""

        approval, end = uuid4(), uuid4()
        issues = self.validate(
            [self.approval_node(approval), self.end_node(end)],
            [self.connection(approval, end)],
        )
        self.assert_has_code(issues, RULE_START_COUNT_INVALID)
        self.assertNotIn(RULE_NODE_UNREACHABLE, self.codes(issues))


class ConnectionConditionRuleTestCase(ValidationTestCase):
    """条件分支规则。"""

    def test_multiple_connections_without_condition_is_reported(self) -> None:
        """多条同源连线缺少条件时报出规则码。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [
                self.connection(start, approval),
                self.connection(approval, end),
                self.connection(approval, start),
            ],
        )
        self.assert_has_code(issues, RULE_CONNECTION_CONDITION_REQUIRED)

    def test_duplicate_default_connection_is_reported(self) -> None:
        """同一来源存在两条默认连线时报出规则码。"""

        start, approval, end, other_end = uuid4(), uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [
                self.start_node(start),
                self.approval_node(approval),
                self.end_node(end),
                self.end_node(other_end, name="结束二"),
            ],
            [
                self.connection(start, approval),
                self.connection(approval, end, is_default=True),
                self.connection(approval, other_end, is_default=True),
            ],
        )
        self.assert_has_code(issues, RULE_CONNECTION_DEFAULT_DUPLICATE)

    def test_default_with_condition_is_reported(self) -> None:
        """同一条连线不能既是默认路径又带条件。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [
                self.connection(start, approval),
                self.connection(
                    approval,
                    end,
                    is_default=True,
                    condition={
                        "field": "approval_form.amount",
                        "operator": "GT",
                        "value": 1,
                    },
                ),
            ],
        )
        self.assert_has_code(issues, RULE_CONNECTION_DEFAULT_WITH_CONDITION)

    def test_unknown_condition_field_is_reported(self) -> None:
        """条件字段不存在于审批表单时报出规则码。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [
                self.connection(start, approval),
                self.connection(
                    approval,
                    end,
                    condition={
                        "field": "approval_form.missing_field",
                        "operator": "EQ",
                        "value": 1,
                    },
                ),
            ],
        )
        self.assert_has_code(issues, RULE_CONNECTION_FIELD_UNKNOWN)

    def test_condition_field_without_prefix_is_reported(self) -> None:
        """条件字段必须以 approval_form. 开头。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [
                self.connection(start, approval),
                self.connection(
                    approval,
                    end,
                    condition={"field": "amount", "operator": "EQ", "value": 1},
                ),
            ],
        )
        self.assert_has_code(issues, RULE_CONNECTION_FIELD_UNKNOWN)

    def test_ordering_operator_on_plain_string_is_reported(self) -> None:
        """普通字符串字段不支持大小比较。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [
                self.connection(start, approval),
                self.connection(
                    approval,
                    end,
                    condition={
                        "field": "approval_form.reason",
                        "operator": "GT",
                        "value": "abc",
                    },
                ),
            ],
        )
        self.assert_has_code(issues, RULE_CONNECTION_OPERATOR_INCOMPATIBLE)

    def test_ordering_operator_on_boolean_is_reported(self) -> None:
        """布尔字段不支持大小比较。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [
                self.connection(start, approval),
                self.connection(
                    approval,
                    end,
                    condition={
                        "field": "approval_form.flag",
                        "operator": "GT",
                        "value": True,
                    },
                ),
            ],
        )
        self.assert_has_code(issues, RULE_CONNECTION_OPERATOR_INCOMPATIBLE)

    def test_ordering_operator_on_date_string_is_valid(self) -> None:
        """带 date 格式的字符串字段支持大小比较。"""

        start, approval, end, fallback_end = uuid4(), uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [
                self.start_node(start),
                self.approval_node(approval),
                self.end_node(end),
                self.end_node(
                    fallback_end,
                    result_status="REJECTED",
                    name="默认结束",
                ),
            ],
            [
                self.connection(start, approval),
                self.connection(
                    approval,
                    end,
                    condition={
                        "field": "approval_form.submit_date",
                        "operator": "GTE",
                        "value": "2026-01-01",
                    },
                ),
                self.connection(approval, fallback_end, is_default=True),
            ],
        )
        self.assertEqual(issues, [])

    def test_number_field_with_string_value_is_reported(self) -> None:
        """数字字段传入字符串取值时报出规则码。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [
                self.connection(start, approval),
                self.connection(
                    approval,
                    end,
                    condition={
                        "field": "approval_form.amount",
                        "operator": "EQ",
                        "value": "100",
                    },
                ),
            ],
        )
        self.assert_has_code(issues, RULE_CONNECTION_OPERATOR_INCOMPATIBLE)

    def test_boolean_field_with_integer_value_is_reported(self) -> None:
        """布尔字段不能接受整数取值，bool 是 int 子类不能误判。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [
                self.connection(start, approval),
                self.connection(
                    approval,
                    end,
                    condition={
                        "field": "approval_form.flag",
                        "operator": "EQ",
                        "value": 1,
                    },
                ),
            ],
        )
        self.assert_has_code(issues, RULE_CONNECTION_OPERATOR_INCOMPATIBLE)

    def test_in_operator_with_non_array_value_is_reported(self) -> None:
        """IN 操作符的比较值必须是数组。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [
                self.connection(start, approval),
                self.connection(
                    approval,
                    end,
                    condition={
                        "field": "approval_form.level",
                        "operator": "IN",
                        "value": "URGENT",
                    },
                ),
            ],
        )
        self.assert_has_code(issues, RULE_CONNECTION_CONDITION_INVALID)

    def test_in_operator_with_empty_array_is_reported(self) -> None:
        """IN 操作符不接受空数组。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [
                self.connection(start, approval),
                self.connection(
                    approval,
                    end,
                    condition={
                        "field": "approval_form.level",
                        "operator": "IN",
                        "value": [],
                    },
                ),
            ],
        )
        self.assert_has_code(issues, RULE_CONNECTION_CONDITION_INVALID)

    def test_in_operator_value_outside_enum_is_reported(self) -> None:
        """IN 数组中的每个取值都必须属于字段枚举。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [
                self.connection(start, approval),
                self.connection(
                    approval,
                    end,
                    condition={
                        "field": "approval_form.level",
                        "operator": "IN",
                        "value": ["URGENT", "CRITICAL"],
                    },
                ),
            ],
        )
        self.assert_has_code(issues, RULE_CONNECTION_VALUE_NOT_IN_ENUM)

    def test_not_in_operator_value_outside_enum_is_reported(self) -> None:
        """NOT_IN 数组中的每个取值同样必须属于字段枚举。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [
                self.connection(start, approval),
                self.connection(
                    approval,
                    end,
                    condition={
                        "field": "approval_form.level",
                        "operator": "NOT_IN",
                        "value": ["CRITICAL"],
                    },
                ),
            ],
        )
        self.assert_has_code(issues, RULE_CONNECTION_VALUE_NOT_IN_ENUM)

    def test_value_outside_enum_is_reported(self) -> None:
        """枚举字段的条件取值超出可选范围时永远不会命中。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [
                self.connection(start, approval),
                self.connection(
                    approval,
                    end,
                    condition={
                        "field": "approval_form.level",
                        "operator": "EQ",
                        "value": "CRITICAL",
                    },
                ),
            ],
        )
        self.assert_has_code(issues, RULE_CONNECTION_VALUE_NOT_IN_ENUM)

    def test_is_empty_with_value_is_reported(self) -> None:
        """IS_EMPTY 不允许携带比较值。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [
                self.connection(start, approval),
                self.connection(
                    approval,
                    end,
                    condition={
                        "field": "approval_form.reason",
                        "operator": "IS_EMPTY",
                        "value": 1,
                    },
                ),
            ],
        )
        self.assert_has_code(issues, RULE_CONNECTION_CONDITION_INVALID)

    def test_ordering_operator_without_value_is_reported(self) -> None:
        """GT 必须提供比较值。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [
                self.connection(start, approval),
                self.connection(
                    approval,
                    end,
                    condition={"field": "approval_form.amount", "operator": "GT"},
                ),
            ],
        )
        self.assert_has_code(issues, RULE_CONNECTION_CONDITION_INVALID)

    def test_unsupported_operator_is_reported(self) -> None:
        """不支持的操作符会被明确拒绝。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        issues = self.validate(
            [self.start_node(start), self.approval_node(approval), self.end_node(end)],
            [
                self.connection(start, approval),
                self.connection(
                    approval,
                    end,
                    condition={
                        "field": "approval_form.amount",
                        "operator": "LIKE",
                        "value": 1,
                    },
                ),
            ],
        )
        self.assert_has_code(issues, RULE_CONNECTION_CONDITION_INVALID)


class OrchestrationParsingTestCase(ValidationTestCase):
    """编排数据容错。"""

    def test_non_object_orchestration_is_reported(self) -> None:
        """编排不是对象时返回问题而不是抛异常。"""

        connections, issues = parse_connections(["not-a-mapping"])
        self.assertEqual(connections, ())
        self.assert_has_code(issues, RULE_ORCHESTRATION_INVALID)

    def test_connections_not_array_is_reported(self) -> None:
        """connections 不是数组时返回问题而不是抛异常。"""

        connections, issues = parse_connections({"connections": "oops"})
        self.assertEqual(connections, ())
        self.assert_has_code(issues, RULE_ORCHESTRATION_INVALID)

    def test_missing_connections_key_is_allowed(self) -> None:
        """编排缺少 connections 时视为空编排。"""

        connections, issues = parse_connections({})
        self.assertEqual(connections, ())
        self.assertEqual(issues, [])

    def test_connection_without_endpoints_is_reported(self) -> None:
        """连线缺少端点时返回问题而不是抛异常。"""

        connections, issues = parse_connections({"connections": [{"source_node_id": "x"}]})
        self.assertEqual(connections, ())
        self.assert_has_code(issues, RULE_ORCHESTRATION_INVALID)


class FormFieldCollectionTestCase(ValidationTestCase):
    """审批表单字段展开。"""

    def test_fields_are_prefixed_and_nested(self) -> None:
        """字段路径带 approval_form 前缀，嵌套对象用点号展开。"""

        fields = collect_form_fields(FORM_SCHEMA)
        self.assertIn("approval_form.amount", fields)
        self.assertIn("approval_form.payload.nested_amount", fields)

    def test_declared_types_and_format_are_captured(self) -> None:
        """字段类型和字符串格式被抓取，供操作符兼容性判断。"""

        fields = collect_form_fields(FORM_SCHEMA)
        self.assertEqual(fields["approval_form.amount"].types, ("number",))
        self.assertEqual(fields["approval_form.submit_date"].string_format, "date")
        self.assertTrue(fields["approval_form.submit_date"].is_orderable())
        self.assertFalse(fields["approval_form.reason"].is_orderable())

    def test_enum_without_type_is_inferred(self) -> None:
        """没有声明 type 时按 enum 取值反推类型。"""

        fields = collect_form_fields(
            {"type": "object", "properties": {"mode": {"enum": ["A", "B"]}}}
        )
        self.assertEqual(fields["approval_form.mode"].types, ("string",))

    def test_multi_type_declaration_is_supported(self) -> None:
        """type 为数组时保留全部类型。"""

        fields = collect_form_fields(
            {"type": "object", "properties": {"note": {"type": ["string", "null"]}}}
        )
        self.assertEqual(fields["approval_form.note"].types, ("string", "null"))

    def test_non_object_schema_returns_no_fields(self) -> None:
        """非对象表单返回空字段集合而不是抛异常。"""

        self.assertEqual(collect_form_fields(None), {})
        self.assertEqual(collect_form_fields({"type": "object"}), {})


class RemapOrchestrationTestCase(ValidationTestCase):
    """复制流程使用的编排重映射。"""

    def test_endpoints_are_rewritten_and_ids_are_strings(self) -> None:
        """连线两端按映射改写，写回的是字符串形式的 UUID。"""

        start, approval, end = uuid4(), uuid4(), uuid4()
        new_start, new_approval, new_end = uuid4(), uuid4(), uuid4()
        orchestration = {
            "connections": [
                self.connection(start, approval),
                self.connection(
                    approval,
                    end,
                    condition={
                        "field": "approval_form.amount",
                        "operator": "GT",
                        "value": 1,
                    },
                ),
            ]
        }
        remapped = remap_orchestration(
            orchestration,
            {start: new_start, approval: new_approval, end: new_end},
        )

        self.assertEqual(
            remapped["connections"][0],
            {
                "source_node_id": str(new_start),
                "target_node_id": str(new_approval),
            },
        )
        self.assertEqual(remapped["connections"][1]["target_node_id"], str(new_end))
        self.assertEqual(
            remapped["connections"][1]["condition"],
            {"field": "approval_form.amount", "operator": "GT", "value": 1},
        )

    def test_unknown_endpoint_raises(self) -> None:
        """编排引用不属于该流程的节点时拒绝复制。"""

        start, approval, foreign = uuid4(), uuid4(), uuid4()
        with self.assertRaises(ProcessValidationError):
            remap_orchestration(
                {"connections": [self.connection(start, foreign)]},
                {start: uuid4(), approval: uuid4()},
            )

    def test_broken_orchestration_raises(self) -> None:
        """源流程编排结构损坏时拒绝复制。"""

        with self.assertRaises(ProcessValidationError):
            remap_orchestration({"connections": "oops"}, {})


if __name__ == "__main__":
    unittest.main()
