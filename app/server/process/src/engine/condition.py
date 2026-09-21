"""审批运行期的条件判断和路径选择。

这里只做取值和比较，不查询数据库。条件字段在发布时已经校验过存在性和类型兼容性，
运行期需要考虑的是审批单里实际缺失某个字段、或者业务数据与声明类型不一致的情况，
因此所有比较都返回布尔值而不抛异常，由默认路径兜住未命中的情况。

日期、日期时间和时间字段按表单 Schema 声明的 format 解析后再比较，不能直接比较
字符串：同一时刻的不同时区写法（2025-01-01T00:00:00+08:00 与 2024-12-31T18:00:00Z）
字典序和真实时间顺序相反。
"""

from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from app.server.process.src.constants import (
    CONDITION_OPERATOR_RULES,
    FORM_FIELD_PREFIX,
    ORDERABLE_STRING_FORMATS,
)
from app.server.process.src.utils.duration import to_utc

if TYPE_CHECKING:
    # 连线结构只在类型标注中使用，运行期按属性取值，避免与校验模块互相导入。
    from app.server.process.src.service.process_validation import GraphConnection


# 审批单中不存在该字段时使用的哨兵，与“字段值为 null”区分开。
MISSING = object()

_ORDERING_OPERATORS = frozenset({"GT", "GTE", "LT", "LTE"})


def resolve_field_value(approval_form: Mapping[str, Any], field_path: str) -> Any:
    """按 approval_form 前缀的点分路径取出条件字段值。

    路径不合法或中间层不是对象时返回 MISSING，调用方据此判断字段缺失。
    """

    if not isinstance(approval_form, Mapping):
        return MISSING
    if not field_path.startswith(FORM_FIELD_PREFIX):
        return MISSING

    remaining_path = field_path[len(FORM_FIELD_PREFIX) :]
    if not remaining_path:
        return MISSING

    current_value: Any = approval_form
    for segment in remaining_path.split("."):
        if not isinstance(current_value, Mapping) or segment not in current_value:
            return MISSING
        current_value = current_value[segment]
    return current_value


def evaluate_condition(
    condition: Mapping[str, Any],
    approval_form: Mapping[str, Any],
    field_formats: Mapping[str, str | None] | None = None,
) -> bool:
    """判断单个条件是否命中当前审批单。

    field_formats 按字段路径给出表单 Schema 中声明的 format，日期时间字段需要它来
    解析取值，缺少时只能按字符串比较。

    字段缺失按“空值”处理：只有 IS_EMPTY 会命中，其余操作符一律不命中，让流程走
    默认路径，避免条件引用了一个并不存在的字段却静默生效。
    """

    operator = condition.get("operator")
    operator_rule = CONDITION_OPERATOR_RULES.get(operator)
    if operator_rule is None:
        return False

    field_path = str(condition.get("field", ""))
    value = resolve_field_value(approval_form, field_path)

    if operator == "IS_EMPTY":
        return is_empty(value)
    if operator == "NOT_EMPTY":
        return not is_empty(value)

    if value is MISSING:
        return False

    expected = condition.get("value")
    field_format = _resolve_field_format(field_path, field_formats)

    if operator == "EQ":
        return values_equal(value, expected, field_format=field_format)
    if operator == "NE":
        return not values_equal(value, expected, field_format=field_format)
    if operator in _ORDERING_OPERATORS:
        return compare_values(
            operator,
            value,
            expected,
            field_format=field_format,
        )
    if operator in {"IN", "NOT_IN"}:
        matched = any(
            values_equal(value, item, field_format=field_format)
            for item in _iter_items(expected)
        )
        return matched if operator == "IN" else not matched

    return False


def select_next_connection(
    connections: Sequence["GraphConnection"],
    approval_form: Mapping[str, Any],
    field_formats: Mapping[str, str | None] | None = None,
) -> "GraphConnection | None":
    """按编排顺序选择下一条连线。

    connections 必须是同一来源节点的出边并按编排顺序排列。先选第一条命中的条件
    连线，全部未命中时使用唯一的默认路径；只有一条无条件出边时它就是唯一去路。
    """

    matched_condition: "GraphConnection | None" = None
    fallback: "GraphConnection | None" = None

    for connection in connections:
        if connection.condition is not None:
            if matched_condition is None and evaluate_condition(
                connection.condition,
                approval_form,
                field_formats,
            ):
                matched_condition = connection
            continue
        if fallback is None:
            fallback = connection

    return matched_condition or fallback


def parse_temporal(value: Any, field_format: str) -> Any | None:
    """按表单声明的 format 把字符串解析成可比较的时间对象。

    解析失败时返回 None，调用方按不命中处理。date-time 统一换算到 UTC，缺少时区
    信息的取值按 UTC 解释，与系统其它时间处理保持一致。
    """

    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    try:
        if field_format == "date":
            return date.fromisoformat(text)
        if field_format == "time":
            return time.fromisoformat(text)
        return to_utc(datetime.fromisoformat(text))
    except ValueError:
        return None


def _resolve_field_format(
    field_path: str,
    field_formats: Mapping[str, str | None] | None,
) -> str | None:
    """取出字段声明的 format，未提供表单信息时返回 None。"""

    if not field_formats:
        return None
    field_format = field_formats.get(field_path)
    return field_format if isinstance(field_format, str) else None


def is_empty(value: Any) -> bool:
    """判断取值是否为空。字段缺失、null、空字符串、空数组和空对象都算空。"""

    if value is MISSING or value is None:
        return True
    if isinstance(value, str):
        return not value
    if isinstance(value, (list, tuple, dict, set)):
        return not value
    return False


def values_equal(
    left: Any,
    right: Any,
    field_format: str | None = None,
) -> bool:
    """做类型敏感的相等比较，并按字段格式统一日期时间取值。

    日期、日期时间和时间可能使用不同但等价的字符串写法。例如带不同时区的两个
    date-time 字符串可以表示同一时刻，必须解析后再判断是否相等。
    """

    left_is_bool = isinstance(left, bool)
    right_is_bool = isinstance(right, bool)
    if left_is_bool != right_is_bool:
        return False
    if left_is_bool:
        return left is right

    if field_format in ORDERABLE_STRING_FORMATS:
        left_value = parse_temporal(left, field_format)
        right_value = parse_temporal(right, field_format)
        if left_value is None or right_value is None:
            return False
        return left_value == right_value

    if _is_number(left) and _is_number(right):
        return left == right
    return left == right


def compare_values(
    operator: str,
    left: Any,
    right: Any,
    field_format: str | None = None,
) -> bool:
    """执行大小比较，类型不可比较时返回不命中。

    日期字段必须按声明的 format 解析后比较。同为合法时间字符串但时区或写法不同的
    取值（例如 2025-01-01T00:00:00+08:00 与 2024-12-31T18:00:00Z）字典序和真实
    时间顺序相反，直接比较字符串会选错分支。
    """

    if isinstance(left, bool) or isinstance(right, bool):
        return False

    if field_format in ORDERABLE_STRING_FORMATS:
        left_value = parse_temporal(left, field_format)
        right_value = parse_temporal(right, field_format)
        if left_value is None or right_value is None:
            return False
        return _apply_ordering(operator, left_value, right_value)

    both_numbers = _is_number(left) and _is_number(right)
    both_text = isinstance(left, str) and isinstance(right, str)
    if not both_numbers and not both_text:
        return False

    return _apply_ordering(operator, left, right)


def _apply_ordering(operator: str, left: Any, right: Any) -> bool:
    """执行一次大小比较，取值不可排序时返回不命中。"""

    try:
        if operator == "GT":
            return left > right
        if operator == "GTE":
            return left >= right
        if operator == "LT":
            return left < right
        if operator == "LTE":
            return left <= right
    except TypeError:
        # 时区信息不对齐等不可排序的取值按不命中处理，让流程走默认路径。
        return False

    return False


def _is_number(value: Any) -> bool:
    """判断是否为非布尔数字。"""

    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _iter_items(expected: Any) -> tuple[Any, ...]:
    """把 IN 和 NOT_IN 的比较值规整成可遍历的序列。"""

    if isinstance(expected, (list, tuple)):
        return tuple(expected)
    return (expected,) if expected is not None else ()
