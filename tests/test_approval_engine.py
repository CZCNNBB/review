"""审批推进引擎的单元测试，不需要数据库。

覆盖条件判断、路径选择和 AND、OR 节点结果判定三部分纯逻辑。运行期的表单取值可能
缺失或与声明类型不一致，因此这里同时验证各种异常取值的兜底行为。
"""

import unittest
from uuid import uuid4

from app.server.process.src.engine.condition import (
    evaluate_condition,
    is_empty,
    select_next_connection,
    values_equal,
)
from app.server.process.src.engine.nodes import (
    OUTCOME_APPROVED,
    OUTCOME_PENDING,
    OUTCOME_REJECTED,
    resolve_approval_outcome,
)
from app.server.process.src.service.process_validation import GraphConnection


def build_condition(operator: str, value=None, field: str = "approval_form.amount") -> dict:
    """构造一个条件结构。"""

    condition = {"field": field, "operator": operator}
    if value is not None:
        condition["value"] = value
    return condition


def build_connection(
    order_index: int,
    target_node_id=None,
    condition: dict | None = None,
) -> GraphConnection:
    """构造一条校验视图中的连线。

    兜底由"最后一条无条件连线"表达，没有单独的标志位。
    """

    return GraphConnection(
        source_node_id=uuid4(),
        target_node_id=target_node_id or uuid4(),
        condition=condition,
        order_index=order_index,
    )


class ConditionEvaluationTestCase(unittest.TestCase):
    """验证运行期条件取值和比较规则。"""

    def test_equality_operators(self) -> None:
        """EQ 和 NE 按类型敏感的方式比较取值。"""

        approval_form = {"amount": 100, "reason": "采购付款"}
        self.assertTrue(evaluate_condition(build_condition("EQ", 100), approval_form))
        self.assertFalse(evaluate_condition(build_condition("EQ", 99), approval_form))
        self.assertTrue(evaluate_condition(build_condition("EQ", 100.0), approval_form))
        self.assertTrue(evaluate_condition(build_condition("NE", 99), approval_form))
        self.assertFalse(evaluate_condition(build_condition("NE", 100), approval_form))

    def test_number_and_text_are_not_equal(self) -> None:
        """数字取值与内容相同的字符串不相等。"""

        self.assertFalse(values_equal(100, "100"))
        self.assertFalse(
            evaluate_condition(
                build_condition("EQ", "100"),
                {"amount": 100},
            )
        )

    def test_boolean_is_not_integer(self) -> None:
        """布尔值不参与数字比较，避免 True 被当成 1。"""

        self.assertFalse(values_equal(True, 1))
        self.assertTrue(values_equal(True, True))
        self.assertFalse(
            evaluate_condition(
                build_condition("EQ", 1, field="approval_form.urgent"),
                {"urgent": True},
            )
        )

    def test_ordering_operators(self) -> None:
        """GT、GTE、LT、LTE 支持数字和字符串大小比较。"""

        approval_form = {"amount": 10000}
        self.assertTrue(evaluate_condition(build_condition("GT", 9999), approval_form))
        self.assertFalse(evaluate_condition(build_condition("GT", 10000), approval_form))
        self.assertTrue(evaluate_condition(build_condition("GTE", 10000), approval_form))
        self.assertTrue(evaluate_condition(build_condition("LT", 10001), approval_form))
        self.assertTrue(evaluate_condition(build_condition("LTE", 10000), approval_form))

    def test_ordering_on_incomparable_value_does_not_match(self) -> None:
        """取值类型不可比较时不命中，而不是抛异常。"""

        self.assertFalse(
            evaluate_condition(
                build_condition("GT", 100),
                {"amount": "很多"},
            )
        )
        self.assertFalse(
            evaluate_condition(
                build_condition("GT", 100),
                {"amount": None},
            )
        )

    def test_in_and_not_in(self) -> None:
        """IN 和 NOT_IN 按数组包含关系判断。"""

        approval_form = {"type": "PURCHASE"}
        purchase_type = {"field": "approval_form.type"}
        self.assertTrue(
            evaluate_condition(
                build_condition("IN", ["PURCHASE", "SERVICE"], **purchase_type),
                approval_form,
            )
        )
        self.assertFalse(
            evaluate_condition(
                build_condition("IN", ["SERVICE"], **purchase_type),
                approval_form,
            )
        )
        self.assertTrue(
            evaluate_condition(
                build_condition("NOT_IN", ["SERVICE"], **purchase_type),
                approval_form,
            )
        )
        self.assertFalse(
            evaluate_condition(
                build_condition("NOT_IN", ["PURCHASE", "SERVICE"], **purchase_type),
                approval_form,
            )
        )

    def test_empty_operators(self) -> None:
        """IS_EMPTY 和 NOT_EMPTY 把 null、空字符串和空集合都视为空。"""

        self.assertTrue(
            evaluate_condition(
                build_condition("IS_EMPTY", field="approval_form.reason"),
                {"reason": ""},
            )
        )
        self.assertTrue(
            evaluate_condition(
                build_condition("IS_EMPTY", field="approval_form.reason"),
                {"reason": []},
            )
        )
        self.assertTrue(
            evaluate_condition(
                build_condition("IS_EMPTY", field="approval_form.reason"),
                {},
            )
        )
        self.assertTrue(
            evaluate_condition(
                build_condition("NOT_EMPTY", field="approval_form.reason"),
                {"reason": "采购付款"},
            )
        )
        self.assertFalse(
            evaluate_condition(
                build_condition("NOT_EMPTY", field="approval_form.reason"),
                {"reason": None},
            )
        )

    def test_nested_field_path(self) -> None:
        """条件字段支持表单内的嵌套路径。"""

        approval_form = {"customer": {"level": "VIP"}}
        self.assertTrue(
            evaluate_condition(
                build_condition("EQ", "VIP", field="approval_form.customer.level"),
                approval_form,
            )
        )

    def test_missing_field_does_not_match(self) -> None:
        """字段缺失时除 IS_EMPTY 外都不命中，流程走默认路径。"""

        approval_form = {"other": 1}
        for operator, value in (
            ("EQ", 100),
            ("NE", 100),
            ("GT", 1),
            ("IN", [100]),
            ("NOT_IN", [100]),
        ):
            with self.subTest(operator=operator):
                self.assertFalse(
                    evaluate_condition(build_condition(operator, value), approval_form)
                )
        self.assertTrue(
            evaluate_condition(build_condition("IS_EMPTY"), approval_form)
        )

    def test_unknown_operator_does_not_match(self) -> None:
        """未注册的操作符一律不命中。"""

        self.assertFalse(
            evaluate_condition(build_condition("REGEX", "^a"), {"amount": "abc"})
        )

    def test_field_path_without_prefix_does_not_match(self) -> None:
        """条件字段必须以 approval_form 前缀开头。"""

        self.assertFalse(
            evaluate_condition(
                build_condition("EQ", 100, field="amount"),
                {"amount": 100},
            )
        )

    def test_datetime_field_compares_real_time_order(self) -> None:
        """带时区的日期时间按真实时间顺序比较，而不是字典序。"""

        deadline_field = "approval_form.deadline"
        field_formats = {deadline_field: "date-time"}
        # 字典序上 2025-01-01T00:00:00+08:00 更大，实际时间却更早。
        approval_form = {"deadline": "2025-01-01T00:00:00+08:00"}
        condition_value = "2024-12-31T18:00:00Z"

        self.assertFalse(
            evaluate_condition(
                build_condition("GT", condition_value, field=deadline_field),
                approval_form,
                field_formats,
            )
        )
        self.assertTrue(
            evaluate_condition(
                build_condition("LT", condition_value, field=deadline_field),
                approval_form,
                field_formats,
            )
        )

    def test_timezone_offsets_expressing_same_instant_are_equal(self) -> None:
        """不同时区写法表示同一时刻时大小比较结果一致。"""

        deadline_field = "approval_form.deadline"
        field_formats = {deadline_field: "date-time"}
        approval_form = {"deadline": "2025-01-01T08:00:00+08:00"}

        self.assertFalse(
            evaluate_condition(
                build_condition("GT", "2025-01-01T00:00:00Z", field=deadline_field),
                approval_form,
                field_formats,
            )
        )
        self.assertTrue(
            evaluate_condition(
                build_condition("GTE", "2025-01-01T00:00:00Z", field=deadline_field),
                approval_form,
                field_formats,
            )
        )

    def test_temporal_equality_and_membership_use_real_time(self) -> None:
        """日期时间的相等和集合判断按真实时刻处理等价时区写法。"""

        deadline_field = "approval_form.deadline"
        field_formats = {deadline_field: "date-time"}
        approval_form = {"deadline": "2025-01-01T08:00:00+08:00"}
        equivalent_utc_value = "2025-01-01T00:00:00Z"

        expected_results = {
            "EQ": True,
            "NE": False,
            "IN": True,
            "NOT_IN": False,
        }
        for operator, expected_result in expected_results.items():
            condition_value = (
                [equivalent_utc_value]
                if operator in {"IN", "NOT_IN"}
                else equivalent_utc_value
            )
            with self.subTest(operator=operator):
                self.assertEqual(
                    evaluate_condition(
                        build_condition(
                            operator,
                            condition_value,
                            field=deadline_field,
                        ),
                        approval_form,
                        field_formats,
                    ),
                    expected_result,
                )

    def test_naive_datetime_is_treated_as_utc(self) -> None:
        """缺少时区的取值按 UTC 解释，与系统其它时间处理保持一致。"""

        deadline_field = "approval_form.deadline"
        field_formats = {deadline_field: "date-time"}
        approval_form = {"deadline": "2025-01-01T00:00:00"}

        # 缺少时区时按 UTC 解释，因此与同一时刻的 UTC 写法相等。
        self.assertFalse(
            evaluate_condition(
                build_condition("GT", "2025-01-01T00:00:00Z", field=deadline_field),
                approval_form,
                field_formats,
            )
        )
        self.assertTrue(
            evaluate_condition(
                build_condition("GTE", "2025-01-01T00:00:00Z", field=deadline_field),
                approval_form,
                field_formats,
            )
        )
        # 缺少时区按 UTC 解释后仍然能正确比较先后。
        self.assertTrue(
            evaluate_condition(
                build_condition("LT", "2025-01-01T00:01:00Z", field=deadline_field),
                approval_form,
                field_formats,
            )
        )

    def test_date_and_time_formats_are_parsed(self) -> None:
        """date 和 time 字段按各自的格式解析后比较。"""

        self.assertTrue(
            evaluate_condition(
                build_condition("GT", "2025-02-09", field="approval_form.start_date"),
                {"start_date": "2025-02-10"},
                {"approval_form.start_date": "date"},
            )
        )
        self.assertTrue(
            evaluate_condition(
                build_condition("GT", "09:00:00", field="approval_form.start_time"),
                {"start_time": "18:00:00"},
                {"approval_form.start_time": "time"},
            )
        )
        # 带时区的时间字段按真实时刻比较：02:00Z 晚于 09:00+08:00（即 01:00Z），
        # 但字典序更小。
        self.assertTrue(
            evaluate_condition(
                build_condition("GT", "09:00:00+08:00", field="approval_form.start_time"),
                {"start_time": "02:00:00Z"},
                {"approval_form.start_time": "time"},
            )
        )

    def test_unparseable_temporal_value_does_not_match(self) -> None:
        """无法按声明格式解析的取值不命中，避免选出错误分支。"""

        deadline_field = "approval_form.deadline"
        field_formats = {deadline_field: "date-time"}

        for invalid_value in ("不是时间", "", None, 20250101):
            with self.subTest(value=invalid_value):
                self.assertFalse(
                    evaluate_condition(
                        build_condition("GT", "2025-01-01T00:00:00Z", field=deadline_field),
                        {"deadline": invalid_value},
                        field_formats,
                    )
                )

    def test_is_empty_helper(self) -> None:
        """空值判断覆盖常见的空取值。"""

        for empty_value in (None, "", [], {}, ()):
            with self.subTest(value=empty_value):
                self.assertTrue(is_empty(empty_value))
        for filled_value in (0, False, " ", [0], {"a": 1}):
            with self.subTest(value=filled_value):
                self.assertFalse(is_empty(filled_value))


class PathSelectionTestCase(unittest.TestCase):
    """验证按编排顺序选择下一条连线。"""

    def test_first_matching_condition_wins(self) -> None:
        """多条条件命中时取编排顺序最靠前的一条。"""

        first_target = uuid4()
        second_target = uuid4()
        connections = [
            build_connection(
                0,
                target_node_id=first_target,
                condition=build_condition("GT", 100),
            ),
            build_connection(
                1,
                target_node_id=second_target,
                condition=build_condition("GT", 10),
            ),
        ]
        selected = select_next_connection(connections, {"amount": 5000})
        self.assertIsNotNone(selected)
        self.assertEqual(selected.target_node_id, first_target)

    def test_default_is_used_when_no_condition_matches(self) -> None:
        """全部条件未命中时选择默认路径。"""

        default_target = uuid4()
        connections = [
            build_connection(
                0,
                condition=build_condition("GT", 10000),
            ),
            build_connection(1, target_node_id=default_target),
        ]
        selected = select_next_connection(connections, {"amount": 100})
        self.assertIsNotNone(selected)
        self.assertEqual(selected.target_node_id, default_target)

    def test_single_unconditional_connection_is_used(self) -> None:
        """只有一条无条件连线时它就是唯一去路。"""

        target = uuid4()
        connections = [build_connection(0, target_node_id=target)]
        selected = select_next_connection(connections, {})
        self.assertIsNotNone(selected)
        self.assertEqual(selected.target_node_id, target)

    def test_no_connection_returns_none(self) -> None:
        """没有任何后续连线时返回 None，由调用方处理异常编排。"""

        self.assertIsNone(select_next_connection((), {"amount": 1}))

    def test_datetime_condition_selects_correct_path(self) -> None:
        """日期时间条件按真实时间顺序选择分支。"""

        deadline_field = "approval_form.deadline"
        field_formats = {deadline_field: "date-time"}
        conditioned_target = uuid4()
        default_target = uuid4()
        connections = [
            build_connection(
                0,
                target_node_id=conditioned_target,
                condition=build_condition("LT", "2024-12-31T18:00:00Z", field=deadline_field),
            ),
            build_connection(1, target_node_id=default_target),
        ]

        # 该取值实际是 2024-12-31T16:00:00Z，早于条件值，应命中条件分支；
        # 按字符串比较时它更大，会错误地走默认路径。
        selected = select_next_connection(
            connections,
            {"deadline": "2025-01-01T00:00:00+08:00"},
            field_formats,
        )
        self.assertIsNotNone(selected)
        self.assertEqual(selected.target_node_id, conditioned_target)

        # 该取值实际晚于条件值，应走默认路径。
        fallback_selected = select_next_connection(
            connections,
            {"deadline": "2025-01-01T00:00:00Z"},
            field_formats,
        )
        self.assertIsNotNone(fallback_selected)
        self.assertEqual(fallback_selected.target_node_id, default_target)


class ApprovalOutcomeTestCase(unittest.TestCase):
    """验证 AND 和 OR 两种模式下的节点结果判定。"""

    def test_and_mode_waits_for_every_approver(self) -> None:
        """AND 模式必须全部同意才算节点通过。"""

        self.assertEqual(
            resolve_approval_outcome("AND", ["APPROVED", "PENDING"]),
            OUTCOME_PENDING,
        )
        self.assertEqual(
            resolve_approval_outcome("AND", ["APPROVED", "APPROVED"]),
            OUTCOME_APPROVED,
        )

    def test_or_mode_passes_on_first_approval(self) -> None:
        """OR 模式任意一人同意即通过。"""

        self.assertEqual(
            resolve_approval_outcome("OR", ["APPROVED", "PENDING"]),
            OUTCOME_APPROVED,
        )

    def test_rejection_wins_in_both_modes(self) -> None:
        """任意一人拒绝立即形成拒绝结果，且优先于同意。"""

        for approval_mode in ("AND", "OR"):
            with self.subTest(approval_mode=approval_mode):
                self.assertEqual(
                    resolve_approval_outcome(
                        approval_mode,
                        ["APPROVED", "REJECTED"],
                    ),
                    OUTCOME_REJECTED,
                )

    def test_pending_when_nothing_is_handled(self) -> None:
        """全部待处理时节点还没有结果。"""

        self.assertEqual(
            resolve_approval_outcome("AND", ["PENDING", "PENDING"]),
            OUTCOME_PENDING,
        )
        self.assertEqual(
            resolve_approval_outcome("OR", ["PENDING", "PENDING"]),
            OUTCOME_PENDING,
        )

    def test_cancelled_tasks_do_not_complete_and_mode(self) -> None:
        """被取消的任务不参与 AND 模式的全员同意判断。"""

        self.assertEqual(
            resolve_approval_outcome("AND", ["APPROVED", "CANCELLED"]),
            OUTCOME_PENDING,
        )


if __name__ == "__main__":
    unittest.main()
