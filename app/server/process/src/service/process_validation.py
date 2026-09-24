"""审批流完整性校验引擎。

校验分为两层：本模块只做结构校验，不查数据库；节点定义、审批人状态等引用数据
由 Service 批量查询后作为参数传入。所有检查都返回问题列表而不抛首个错误，管理
页面才能一次性展示全部问题。
"""

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence
from uuid import UUID

from app.server.process.src.constants import (
    APPROVAL_MODES,
    BRANCHING_NODE_TYPES,
    CONDITION_OPERATOR_RULES,
    FORM_FIELD_PREFIX,
    MAX_FORM_SCHEMA_DEPTH,
    NODE_DEFINITION_STATUS_ENABLED,
    NODE_TYPE_APPROVAL,
    NODE_TYPE_END,
    NODE_TYPE_START,
    ORCHESTRATION_CONNECTIONS_KEY,
    ORDERABLE_STRING_FORMATS,
    ORDERABLE_TYPES,
    RULE_APPROVAL_MODE_INVALID,
    RULE_APPROVER_DISABLED,
    RULE_APPROVER_DUPLICATE,
    RULE_APPROVER_ID_INVALID,
    RULE_APPROVER_NOT_FOUND,
    RULE_APPROVER_REQUIRED,
    RULE_CONNECTION_CONDITION_INVALID,
    RULE_BRANCH_FALLBACK_INVALID,
    RULE_BRANCH_MISSING_CONDITION,
    RULE_BRANCH_TARGET_REQUIRED,
    RULE_CONNECTION_FIELD_UNKNOWN,
    RULE_CONNECTION_NODE_UNKNOWN,
    RULE_CONNECTION_OPERATOR_INCOMPATIBLE,
    RULE_CONNECTION_VALUE_NOT_IN_ENUM,
    RULE_END_AS_SOURCE,
    RULE_END_REQUIRED,
    RULE_GRAPH_CYCLE,
    RULE_NODE_CONFIG_INVALID,
    RULE_NODE_DEFINITION_DISABLED,
    RULE_NODE_DEFINITION_NOT_FOUND,
    RULE_NODE_TYPE_UNSUPPORTED,
    RULE_NODE_UNREACHABLE,
    RULE_NODE_WITHOUT_OUTGOING,
    RULE_ORCHESTRATION_INVALID,
    RULE_START_AS_TARGET,
    RULE_START_COUNT_INVALID,
    RULE_TOO_MANY_OUTGOING_CONNECTIONS,
)
from app.server.process.src.node_catalog import SUPPORTED_NODE_TYPES
from app.server.process.src.service.exceptions import ProcessValidationError
from app.server.process.src.utils.json_schema import (
    JSON_TYPE_NAMES,
    resolve_json_type,
    validate_instance,
)


# 三色标记使用的节点颜色。
_COLOR_WHITE = 0
_COLOR_GRAY = 1
_COLOR_BLACK = 2

# 审批人配置根路径，用于拼装前端可定位的字段路径。
_APPROVERS_FIELD = "config.approvers"
_APPROVAL_MODE_FIELD = "config.approval_mode"


@dataclass(frozen=True)
class ValidationIssue:
    """一条流程校验问题，前端可按 code 和字段路径定位到画布元素。"""

    code: str
    message: str
    node_id: UUID | None = None
    field: str | None = None
    connection_index: int | None = None


@dataclass(frozen=True)
class GraphNode:
    """校验用的节点视图，只保留判断规则需要的字段。"""

    id: UUID
    node_definition_id: UUID
    name: str
    config: Mapping[str, Any]


@dataclass(frozen=True)
class GraphConnection:
    """校验用的连线视图，把条件分支表达为一条带顺序的连接。

    target_node_id 可以为空：条件分支可以先在节点里定义好，再把线拉到目标节点上，
    "定义好了还没接"是一个合法中间状态，发布前由校验要求补全。
    """

    source_node_id: UUID
    target_node_id: UUID | None
    condition: Mapping[str, Any] | None
    order_index: int


@dataclass(frozen=True)
class ProcessGraph:
    """一条流程的完整校验视图。"""

    form_schema: Mapping[str, Any]
    nodes: tuple[GraphNode, ...] = field(default_factory=tuple)
    connections: tuple[GraphConnection, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FormFieldInfo:
    """审批表单中一个字段的类型信息，用于判断操作符兼容性。"""

    path: str
    types: tuple[str, ...]
    enum_values: tuple[Any, ...]
    string_format: str | None

    def is_orderable(self) -> bool:
        """判断字段是否支持大小比较。"""

        if any(field_type in ORDERABLE_TYPES for field_type in self.types):
            return True
        return (
            "string" in self.types
            and self.string_format in ORDERABLE_STRING_FORMATS
        )

    def accepts_value(self, value: Any) -> bool:
        """判断条件取值是否符合字段声明类型。"""

        # 字段类型无法推断时不做类型兼容判断，只要求字段存在。
        if not self.types:
            return True

        value_type = resolve_json_type(value)
        if value_type in self.types:
            return True
        # 整数取值可以满足数字类型的条件约束。
        if value_type == "integer" and "number" in self.types:
            return True
        return False


# ---------------------------------------------------------------------------
# 组装校验视图
# ---------------------------------------------------------------------------


def build_graph(
    node_inputs: Iterable[tuple[UUID, UUID, str, Any]],
    form_schema: Any,
    orchestration: Any,
) -> tuple[ProcessGraph, list[ValidationIssue]]:
    """把节点记录和编排原始数据组装成校验视图。

    node_inputs 每项依次是节点 ID、节点定义 ID、节点名称和配置，兼容请求模型和
    数据库模型两种来源。编排数据损坏时返回问题列表而不是抛异常。
    """

    connections, issues = parse_connections(orchestration)

    nodes: list[GraphNode] = []
    for node_id, node_definition_id, name, config in node_inputs:
        normalized_config = config if isinstance(config, Mapping) else {}
        nodes.append(
            GraphNode(
                id=node_id,
                node_definition_id=node_definition_id,
                name=name,
                config=normalized_config,
            )
        )

    graph = ProcessGraph(
        form_schema=form_schema if isinstance(form_schema, Mapping) else {},
        nodes=tuple(nodes),
        connections=connections,
    )
    return graph, issues


def parse_connections(
    orchestration: Any,
) -> tuple[tuple[GraphConnection, ...], list[ValidationIssue]]:
    """解析编排数据中的连线，只做结构层面的容错。

    条件字段是否存在、操作符与字段类型是否兼容等需要表单数据的判断放在
    check_connection_conditions 中完成。
    """

    issues: list[ValidationIssue] = []

    if orchestration is None:
        return (), issues
    if not isinstance(orchestration, Mapping):
        issues.append(
            ValidationIssue(
                code=RULE_ORCHESTRATION_INVALID,
                message="流程编排必须是对象",
                field="orchestration",
            )
        )
        return (), issues

    raw_connections = orchestration.get(ORCHESTRATION_CONNECTIONS_KEY)
    if raw_connections is None:
        return (), issues
    if not isinstance(raw_connections, Sequence) or isinstance(raw_connections, str):
        issues.append(
            ValidationIssue(
                code=RULE_ORCHESTRATION_INVALID,
                message="流程编排的 connections 必须是数组",
                field="orchestration.connections",
            )
        )
        return (), issues

    connections: list[GraphConnection] = []
    for order_index, raw_connection in enumerate(raw_connections):
        position_text = f"第 {order_index + 1} 条连线"

        if not isinstance(raw_connection, Mapping):
            issues.append(
                ValidationIssue(
                    code=RULE_ORCHESTRATION_INVALID,
                    message=f"{position_text}必须是对象",
                    connection_index=order_index,
                )
            )
            continue

        source_node_id = _parse_uuid(raw_connection.get("source_node_id"))
        raw_target = raw_connection.get("target_node_id")
        # 目标允许为空：分支可以先定义好，之后再拉线到目标节点
        target_node_id = None if raw_target in (None, "") else _parse_uuid(raw_target)

        if source_node_id is None:
            issues.append(
                ValidationIssue(
                    code=RULE_ORCHESTRATION_INVALID,
                    message=f"{position_text}的来源节点 ID 不是有效的 UUID",
                    field="orchestration.connections.source_node_id",
                    connection_index=order_index,
                )
            )
        if raw_target not in (None, "") and target_node_id is None:
            issues.append(
                ValidationIssue(
                    code=RULE_ORCHESTRATION_INVALID,
                    message=f"{position_text}的目标节点 ID 不是有效的 UUID",
                    field="orchestration.connections.target_node_id",
                    connection_index=order_index,
                )
            )

        # 这里不再读取旧版本写入的 default 标志位：分支的兜底由"最后一条出线"表达，
        # 标志位留在旧数据里也不会影响校验和运行。
        condition = _parse_condition(raw_connection.get("condition"), position_text, order_index, issues)

        if source_node_id is None:
            continue

        connections.append(
            GraphConnection(
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                condition=condition,
                order_index=order_index,
            )
        )

    return tuple(connections), issues


def _parse_condition(
    raw_condition: Any,
    position_text: str,
    order_index: int,
    issues: list[ValidationIssue],
) -> Mapping[str, Any] | None:
    """解析并校验单个条件的结构，非法时追加问题并返回 None。"""

    if raw_condition is None:
        return None
    if not isinstance(raw_condition, Mapping):
        issues.append(
            ValidationIssue(
                code=RULE_CONNECTION_CONDITION_INVALID,
                message=f"{position_text}的条件必须是对象",
                connection_index=order_index,
            )
        )
        return None

    raw_field = raw_condition.get("field")
    if not isinstance(raw_field, str) or not raw_field.strip():
        issues.append(
            ValidationIssue(
                code=RULE_CONNECTION_CONDITION_INVALID,
                message=f"{position_text}的条件缺少有效的字段路径",
                connection_index=order_index,
            )
        )
        return None

    raw_operator = raw_condition.get("operator")
    if not isinstance(raw_operator, str) or raw_operator not in CONDITION_OPERATOR_RULES:
        supported_operators = "、".join(CONDITION_OPERATOR_RULES)
        issues.append(
            ValidationIssue(
                code=RULE_CONNECTION_CONDITION_INVALID,
                message=(
                    f"{position_text}的条件操作符 {raw_operator} 不受支持，"
                    f"可选值为 {supported_operators}"
                ),
                connection_index=order_index,
            )
        )
        return None

    operator_rule = CONDITION_OPERATOR_RULES[raw_operator]
    has_value = "value" in raw_condition
    raw_value = raw_condition.get("value")

    if operator_rule.requires_value and not has_value:
        issues.append(
            ValidationIssue(
                code=RULE_CONNECTION_CONDITION_INVALID,
                message=f"{position_text}的条件操作符 {raw_operator} 必须提供比较值",
                connection_index=order_index,
            )
        )
        return None

    # 不允许的字段静默忽略会让前端误以为条件生效，因此直接报错。
    if not operator_rule.requires_value and has_value:
        issues.append(
            ValidationIssue(
                code=RULE_CONNECTION_CONDITION_INVALID,
                message=f"{position_text}的条件操作符 {raw_operator} 不允许携带比较值",
                connection_index=order_index,
            )
        )
        return None

    if operator_rule.value_must_be_array:
        if (
            not isinstance(raw_value, Sequence)
            or isinstance(raw_value, str)
            or not raw_value
        ):
            issues.append(
                ValidationIssue(
                    code=RULE_CONNECTION_CONDITION_INVALID,
                    message=f"{position_text}的条件操作符 {raw_operator} 需要非空的比较值数组",
                    connection_index=order_index,
                )
            )
            return None

    return {
        "field": raw_field.strip(),
        "operator": raw_operator,
        **({"value": raw_value} if has_value else {}),
    }


# ---------------------------------------------------------------------------
# 表单字段展开
# ---------------------------------------------------------------------------


def collect_form_fields(form_schema: Any) -> dict[str, FormFieldInfo]:
    """展开审批表单 Schema 的字段类型，键为带 approval_form 前缀的字段路径。"""

    fields: dict[str, FormFieldInfo] = {}
    if not isinstance(form_schema, Mapping):
        return fields

    properties = form_schema.get("properties")
    if not isinstance(properties, Mapping):
        return fields

    _collect_properties(properties, prefix="", fields=fields, depth=0)
    return fields


def _collect_properties(
    properties: Mapping[str, Any],
    prefix: str,
    fields: dict[str, FormFieldInfo],
    depth: int,
) -> None:
    """递归展开 properties，限制深度以防御自引用结构。"""

    if depth >= MAX_FORM_SCHEMA_DEPTH:
        return

    for field_name, sub_schema in properties.items():
        if not isinstance(sub_schema, Mapping):
            continue

        field_path = f"{FORM_FIELD_PREFIX}{prefix}{field_name}"
        enum_values = sub_schema.get("enum")
        normalized_enum = (
            tuple(enum_values)
            if isinstance(enum_values, (list, tuple))
            else ()
        )
        string_format = sub_schema.get("format")
        fields[field_path] = FormFieldInfo(
            path=field_path,
            types=_resolve_field_types(sub_schema),
            enum_values=normalized_enum,
            string_format=string_format if isinstance(string_format, str) else None,
        )

        nested_properties = sub_schema.get("properties")
        if isinstance(nested_properties, Mapping):
            _collect_properties(
                nested_properties,
                prefix=f"{prefix}{field_name}.",
                fields=fields,
                depth=depth + 1,
            )


def _resolve_field_types(sub_schema: Mapping[str, Any]) -> tuple[str, ...]:
    """推断字段的 JSON Schema 类型，缺失时按 enum 反推。"""

    declared_type = sub_schema.get("type")
    if isinstance(declared_type, str):
        return (declared_type,)
    if isinstance(declared_type, (list, tuple)):
        return tuple(str(item) for item in declared_type)

    enum_values = sub_schema.get("enum")
    if isinstance(enum_values, (list, tuple)):
        inferred: list[str] = []
        for value in enum_values:
            type_name = resolve_json_type(value)
            if type_name not in inferred:
                inferred.append(type_name)
        return tuple(inferred)

    return ()


# ---------------------------------------------------------------------------
# 主校验入口
# ---------------------------------------------------------------------------


def validate_graph(
    graph: ProcessGraph,
    *,
    definitions: Mapping[UUID, Any],
    person_statuses: Mapping[UUID, str],
    include_persons: bool = True,
) -> list[ValidationIssue]:
    """执行全部结构校验，返回去重后的完整问题列表。"""

    node_types = _resolve_node_types(graph, definitions)

    issues: list[ValidationIssue] = []
    issues.extend(check_node_definitions(graph, definitions))
    issues.extend(check_node_configs(graph, definitions))
    issues.extend(check_approvers(graph, node_types, person_statuses, include_persons))
    issues.extend(check_start_and_end(graph, node_types))
    issues.extend(check_connection_endpoints(graph, node_types))
    issues.extend(check_topology(graph, node_types))
    issues.extend(check_connection_conditions(graph, node_types))

    return _deduplicate_issues(issues)


def _resolve_node_types(
    graph: ProcessGraph,
    definitions: Mapping[UUID, Any],
) -> dict[UUID, str]:
    """把节点实例映射到节点定义声明的后端执行类型。

    节点定义缺失或类型不受支持时不会出现在结果里，这些节点不参与 START、END 和
    拓扑规则，避免级联报错淹没真正的问题。
    """

    node_types: dict[UUID, str] = {}
    for node in graph.nodes:
        definition = definitions.get(node.node_definition_id)
        if definition is None:
            continue
        if definition.node_type not in SUPPORTED_NODE_TYPES:
            continue
        node_types[node.id] = definition.node_type
    return node_types


def _deduplicate_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    """按规则码和定位信息去重，保持各子检查的产出顺序。"""

    deduplicated: list[ValidationIssue] = []
    seen: set[tuple[Any, ...]] = set()
    for issue in issues:
        key = (issue.code, issue.node_id, issue.field, issue.connection_index, issue.message)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(issue)
    return deduplicated


# ---------------------------------------------------------------------------
# 各条校验规则
# ---------------------------------------------------------------------------


def check_node_definitions(
    graph: ProcessGraph,
    definitions: Mapping[UUID, Any],
) -> list[ValidationIssue]:
    """校验节点引用的节点定义存在、已启用且类型受后端支持。"""

    issues: list[ValidationIssue] = []
    for node in graph.nodes:
        definition = definitions.get(node.node_definition_id)
        if definition is None:
            issues.append(
                ValidationIssue(
                    code=RULE_NODE_DEFINITION_NOT_FOUND,
                    message=f"节点「{node.name}」引用的节点定义不存在",
                    node_id=node.id,
                )
            )
            continue
        if definition.status != NODE_DEFINITION_STATUS_ENABLED:
            issues.append(
                ValidationIssue(
                    code=RULE_NODE_DEFINITION_DISABLED,
                    message=f"节点「{node.name}」引用的节点定义「{definition.name}」已停用",
                    node_id=node.id,
                )
            )
        if definition.node_type not in SUPPORTED_NODE_TYPES:
            supported_types = "、".join(sorted(SUPPORTED_NODE_TYPES))
            issues.append(
                ValidationIssue(
                    code=RULE_NODE_TYPE_UNSUPPORTED,
                    message=(
                        f"节点「{node.name}」引用的节点定义类型 {definition.node_type} "
                        f"不受后端支持，可选值为 {supported_types}"
                    ),
                    node_id=node.id,
                )
            )
    return issues


def check_node_configs(
    graph: ProcessGraph,
    definitions: Mapping[UUID, Any],
) -> list[ValidationIssue]:
    """按节点定义的 config_schema_json 校验节点实例配置。"""

    issues: list[ValidationIssue] = []
    for node in graph.nodes:
        definition = definitions.get(node.node_definition_id)
        if definition is None:
            continue

        schema = definition.config_schema_json
        if not isinstance(schema, Mapping) or not schema:
            continue

        for config_issue in validate_instance(node.config, schema):
            if config_issue.path == "config":
                message = f"节点「{node.name}」配置错误：{config_issue.message}"
            else:
                location = config_issue.path.removeprefix("config.")
                message = f"节点「{node.name}」配置项 {location}：{config_issue.message}"
            issues.append(
                ValidationIssue(
                    code=RULE_NODE_CONFIG_INVALID,
                    message=message,
                    node_id=node.id,
                    field=config_issue.path,
                )
            )
    return issues


def check_approvers(
    graph: ProcessGraph,
    node_types: Mapping[UUID, str],
    person_statuses: Mapping[UUID, str],
    include_persons: bool,
) -> list[ValidationIssue]:
    """校验人工审批节点的审批模式和审批人配置。"""

    issues: list[ValidationIssue] = []
    for node in graph.nodes:
        if node_types.get(node.id) != NODE_TYPE_APPROVAL:
            continue

        approval_mode = node.config.get("approval_mode")
        if approval_mode not in APPROVAL_MODES:
            issues.append(
                ValidationIssue(
                    code=RULE_APPROVAL_MODE_INVALID,
                    message=f"节点「{node.name}」的审批模式必须是 AND 或 OR",
                    node_id=node.id,
                    field=_APPROVAL_MODE_FIELD,
                )
            )

        raw_approvers = node.config.get("approvers")
        if not isinstance(raw_approvers, Sequence) or isinstance(raw_approvers, str) or not raw_approvers:
            issues.append(
                ValidationIssue(
                    code=RULE_APPROVER_REQUIRED,
                    message=f"节点「{node.name}」至少需要配置一名审批人",
                    node_id=node.id,
                    field=_APPROVERS_FIELD,
                )
            )
            continue

        seen_person_ids: set[UUID] = set()
        for approver_index, raw_approver in enumerate(raw_approvers):
            field_path = f"{_APPROVERS_FIELD}[{approver_index}].person_id"
            if not isinstance(raw_approver, Mapping):
                issues.append(
                    ValidationIssue(
                        code=RULE_APPROVER_ID_INVALID,
                        message=f"节点「{node.name}」第 {approver_index + 1} 名审批人的配置格式错误",
                        node_id=node.id,
                        field=field_path,
                    )
                )
                continue

            person_id = _parse_uuid(raw_approver.get("person_id"))
            if person_id is None:
                issues.append(
                    ValidationIssue(
                        code=RULE_APPROVER_ID_INVALID,
                        message=(
                            f"节点「{node.name}」第 {approver_index + 1} 名审批人的"
                            "人员 ID 不是有效的 UUID"
                        ),
                        node_id=node.id,
                        field=field_path,
                    )
                )
                continue

            if person_id in seen_person_ids:
                issues.append(
                    ValidationIssue(
                        code=RULE_APPROVER_DUPLICATE,
                        message=f"节点「{node.name}」存在重复的审批人",
                        node_id=node.id,
                        field=field_path,
                    )
                )
                continue
            seen_person_ids.add(person_id)

            if not include_persons:
                continue

            person_status = person_statuses.get(person_id)
            if person_status is None:
                issues.append(
                    ValidationIssue(
                        code=RULE_APPROVER_NOT_FOUND,
                        message=f"节点「{node.name}」的审批人 {person_id} 不存在",
                        node_id=node.id,
                        field=field_path,
                    )
                )
            elif person_status != "ENABLED":
                issues.append(
                    ValidationIssue(
                        code=RULE_APPROVER_DISABLED,
                        message=f"节点「{node.name}」的审批人 {person_id} 已停用",
                        node_id=node.id,
                        field=field_path,
                    )
                )
    return issues


def check_start_and_end(
    graph: ProcessGraph,
    node_types: Mapping[UUID, str],
) -> list[ValidationIssue]:
    """校验开始节点数量、结束节点数量。"""

    issues: list[ValidationIssue] = []

    start_nodes = [node for node in graph.nodes if node_types.get(node.id) == NODE_TYPE_START]
    if len(start_nodes) != 1:
        if not start_nodes:
            message = "流程必须且只能包含一个开始节点，当前没有任何开始节点"
        else:
            message = (
                f"流程必须且只能包含一个开始节点，当前存在 {len(start_nodes)} 个"
            )
        issues.append(
            ValidationIssue(code=RULE_START_COUNT_INVALID, message=message)
        )

    end_nodes = [node for node in graph.nodes if node_types.get(node.id) == NODE_TYPE_END]
    if not end_nodes:
        issues.append(
            ValidationIssue(
                code=RULE_END_REQUIRED,
                message="流程至少需要一个结束节点",
            )
        )
        return issues

    # 结束节点没有配置项：走到它就是审批通过、流程完成。审批被拒绝由审批人在
    # 人工审批节点当场结束实例，不会走结束节点。
    return issues


def check_connection_endpoints(
    graph: ProcessGraph,
    node_types: Mapping[UUID, str],
) -> list[ValidationIssue]:
    """校验连线两端节点属于当前流程，且开始节点和结束节点不在非法位置。"""

    issues: list[ValidationIssue] = []
    node_ids = {node.id for node in graph.nodes}

    for connection in graph.connections:
        position_text = f"第 {connection.order_index + 1} 条连线"

        if connection.source_node_id not in node_ids:
            issues.append(
                ValidationIssue(
                    code=RULE_CONNECTION_NODE_UNKNOWN,
                    message=f"{position_text}的来源节点不属于当前流程",
                    connection_index=connection.order_index,
                )
            )
        # 还没接目标的连线由"分支未接去向"规则报出，这里跳过目标相关判断
        if connection.target_node_id is not None:
            if connection.target_node_id not in node_ids:
                issues.append(
                    ValidationIssue(
                        code=RULE_CONNECTION_NODE_UNKNOWN,
                        message=f"{position_text}的目标节点不属于当前流程",
                        connection_index=connection.order_index,
                    )
                )
            if node_types.get(connection.target_node_id) == NODE_TYPE_START:
                issues.append(
                    ValidationIssue(
                        code=RULE_START_AS_TARGET,
                        message=f"{position_text}把开始节点作为目标节点",
                        node_id=connection.target_node_id,
                        connection_index=connection.order_index,
                    )
                )
        if node_types.get(connection.source_node_id) == NODE_TYPE_END:
            issues.append(
                ValidationIssue(
                    code=RULE_END_AS_SOURCE,
                    message=f"{position_text}把结束节点作为来源节点",
                    node_id=connection.source_node_id,
                    connection_index=connection.order_index,
                )
            )

    return issues


def check_topology(
    graph: ProcessGraph,
    node_types: Mapping[UUID, str],
) -> list[ValidationIssue]:
    """校验节点可达性、非结束节点的出边和流程图中的环。"""

    issues: list[ValidationIssue] = []
    adjacency = _build_adjacency(graph)

    for node in graph.nodes:
        # 节点定义缺失或类型未知的节点已经报过其它错误，这里不再重复报出边问题。
        if node.id not in node_types:
            continue
        if node_types[node.id] == NODE_TYPE_END:
            continue
        if not adjacency.get(node.id):
            issues.append(
                ValidationIssue(
                    code=RULE_NODE_WITHOUT_OUTGOING,
                    message=f"节点「{node.name}」没有任何后续连线，流程会在此中断",
                    node_id=node.id,
                )
            )

    # 只有恰好一个开始节点时才能判断可达性，否则会产生大量无意义的不可达报错。
    start_nodes = [node for node in graph.nodes if node_types.get(node.id) == NODE_TYPE_START]
    if len(start_nodes) == 1:
        reachable_node_ids = _collect_reachable(adjacency, start_nodes[0].id)
        for node in graph.nodes:
            if node.id not in node_types:
                continue
            if node.id not in reachable_node_ids:
                issues.append(
                    ValidationIssue(
                        code=RULE_NODE_UNREACHABLE,
                        message=f"节点「{node.name}」无法从开始节点到达",
                        node_id=node.id,
                    )
                )

    node_names = {node.id: node.name for node in graph.nodes}
    ordered_node_ids = [node.id for node in graph.nodes]
    for cycle_node_ids in _find_cycles(adjacency, ordered_node_ids):
        cycle_names = [node_names[node_id] for node_id in cycle_node_ids]
        cycle_text = " → ".join([*cycle_names, cycle_names[0]])
        issues.append(
            ValidationIssue(
                code=RULE_GRAPH_CYCLE,
                message=f"流程中不允许形成环：{cycle_text}",
                node_id=cycle_node_ids[0],
            )
        )

    return issues


def check_connection_conditions(
    graph: ProcessGraph,
    node_types: Mapping[UUID, str] | None = None,
) -> list[ValidationIssue]:
    """校验同源连线上的条件分支规则和条件内容。"""

    issues: list[ValidationIssue] = []
    form_fields = collect_form_fields(graph.form_schema)
    node_names = {node.id: node.name for node in graph.nodes}
    types = node_types or {}

    connections_by_source: dict[UUID, list[GraphConnection]] = defaultdict(list)
    for connection in graph.connections:
        connections_by_source[connection.source_node_id].append(connection)

    for source_node_id, connections in connections_by_source.items():
        source_name = node_names.get(source_node_id, str(source_node_id))
        source_type = types.get(source_node_id)

        # 分流只允许从条件分支节点出去。普通节点出现多条出线、条件出线或兜底标记，
        # 都说明分流画错了位置：运行时会永远只走第一条，属于很难察觉的错误。
        # 这一类问题由下面这条规则统一报出，后面的分支规则对它不适用，避免误导。
        if source_type is not None and source_type not in BRANCHING_NODE_TYPES:
            if len(connections) > 1 or any(
                connection.condition is not None for connection in connections
            ):
                issues.append(
                    ValidationIssue(
                        code=RULE_TOO_MANY_OUTGOING_CONNECTIONS,
                        message=(
                            f"节点「{source_name}」不允许分流：只有条件分支节点可以有多条出线"
                            "或带条件的出线，请先连到一个条件分支节点，再从那里分支"
                        ),
                        node_id=source_node_id,
                    )
                )
            continue

        # 条件分支节点的出线按顺序表达一条 if/elif/else 阶梯：前面每条都要有条件，
        # 最后一条是"其余情况"，不能带条件。最后一条兜住所有条件都不满足的情况，
        # 缺了它引擎会选不出下一个节点，所以这里不能用"有没有兜底"以外的写法。
        if source_type in BRANCHING_NODE_TYPES:
            last_position = len(connections) - 1
            for position, connection in enumerate(connections):
                if connection.target_node_id is None:
                    issues.append(
                        ValidationIssue(
                            code=RULE_BRANCH_TARGET_REQUIRED,
                            message=(
                                f"节点「{source_name}」的第 {position + 1} 条分支还没有接去向，"
                                "从分支行右侧的圆点拉一条线到目标节点"
                            ),
                            node_id=source_node_id,
                            connection_index=connection.order_index,
                        )
                    )
                if position == last_position:
                    if connection.condition is not None:
                        issues.append(
                            ValidationIssue(
                                code=RULE_BRANCH_FALLBACK_INVALID,
                                message=(
                                    f"节点「{source_name}」的最后一条连线是"
                                    "“其余情况”，用来兜住条件都不满足的时候，不能配条件"
                                ),
                                node_id=source_node_id,
                                connection_index=connection.order_index,
                            )
                        )
                    continue
                if connection.condition is None:
                    issues.append(
                        ValidationIssue(
                            code=RULE_BRANCH_MISSING_CONDITION,
                            message=(
                                f"节点「{source_name}」的第 {position + 1} 条连线要配条件；"
                                "只有最后一条才是“其余情况”"
                            ),
                            node_id=source_node_id,
                            connection_index=connection.order_index,
                        )
                    )

    for connection in graph.connections:
        if connection.condition is None:
            continue
        issues.extend(_check_condition(connection, form_fields))

    return issues


def _check_condition(
    connection: GraphConnection,
    form_fields: Mapping[str, FormFieldInfo],
) -> list[ValidationIssue]:
    """校验单条连线条件引用的字段和操作符是否与表单匹配。"""

    condition = connection.condition
    if condition is None:
        return []

    issues: list[ValidationIssue] = []
    position_text = f"第 {connection.order_index + 1} 条连线"
    field_path = str(condition["field"])
    operator = str(condition["operator"])
    operator_rule = CONDITION_OPERATOR_RULES[operator]

    if not field_path.startswith(FORM_FIELD_PREFIX):
        issues.append(
            ValidationIssue(
                code=RULE_CONNECTION_FIELD_UNKNOWN,
                message=(
                    f"{position_text}的条件字段必须以 {FORM_FIELD_PREFIX} 开头，"
                    "用于指向审批表单中的字段"
                ),
                connection_index=connection.order_index,
            )
        )
        return issues

    field_info = form_fields.get(field_path)
    if field_info is None:
        issues.append(
            ValidationIssue(
                code=RULE_CONNECTION_FIELD_UNKNOWN,
                message=f"{position_text}的条件字段 {field_path} 不存在于审批表单",
                connection_index=connection.order_index,
            )
        )
        return issues

    if operator_rule.supports_ordering and not field_info.is_orderable():
        issues.append(
            ValidationIssue(
                code=RULE_CONNECTION_OPERATOR_INCOMPATIBLE,
                message=(
                    f"{position_text}的条件字段 {field_path} 不支持 {operator} 比较，"
                    "只有数字、整数或日期时间字段可以参与大小比较"
                ),
                connection_index=connection.order_index,
            )
        )
        return issues

    raw_value = condition.get("value")
    if operator_rule.value_must_be_array:
        for item in raw_value:
            if not field_info.accepts_value(item):
                issues.append(
                    ValidationIssue(
                        code=RULE_CONNECTION_OPERATOR_INCOMPATIBLE,
                        message=(
                            f"{position_text}的条件取值 {item} 与字段 {field_path} "
                            f"的类型（{_describe_field_types(field_info)}）不匹配"
                        ),
                        connection_index=connection.order_index,
                    )
                )
                break

            # IN 和 NOT_IN 的每个元素都必须落在字段枚举范围内，不能只校验 JSON 类型。
            if field_info.enum_values and item not in field_info.enum_values:
                choices = "、".join(str(choice) for choice in field_info.enum_values)
                issues.append(
                    ValidationIssue(
                        code=RULE_CONNECTION_VALUE_NOT_IN_ENUM,
                        message=(
                            f"{position_text}的条件取值 {item} 不在字段 {field_path} "
                            f"的可选值（{choices}）范围内"
                        ),
                        connection_index=connection.order_index,
                    )
                )
                break
        return issues

    if operator_rule.requires_value and not field_info.accepts_value(raw_value):
        issues.append(
            ValidationIssue(
                code=RULE_CONNECTION_OPERATOR_INCOMPATIBLE,
                message=(
                    f"{position_text}的条件取值 {raw_value} 与字段 {field_path} "
                    f"的类型（{_describe_field_types(field_info)}）不匹配"
                ),
                connection_index=connection.order_index,
            )
        )
        return issues

    # 枚举外的取值永远不会命中，属于配置错误而不是运行时问题。
    if (
        operator_rule.requires_value
        and field_info.enum_values
        and raw_value not in field_info.enum_values
    ):
        choices = "、".join(str(item) for item in field_info.enum_values)
        issues.append(
            ValidationIssue(
                code=RULE_CONNECTION_VALUE_NOT_IN_ENUM,
                message=(
                    f"{position_text}的条件取值 {raw_value} 不在字段 {field_path} "
                    f"的可选值（{choices}）范围内"
                ),
                connection_index=connection.order_index,
            )
        )

    return issues


def _describe_field_types(field_info: FormFieldInfo) -> str:
    """把字段类型渲染成中文提示。"""

    if not field_info.types:
        return "未声明"

    type_names: list[str] = []
    for field_type in field_info.types:
        if field_type == "string" and field_info.string_format:
            type_names.append(f"字符串（{field_info.string_format}）")
        else:
            type_names.append(JSON_TYPE_NAMES.get(field_type, field_type))
    return "、".join(type_names)


# ---------------------------------------------------------------------------
# 图遍历工具
# ---------------------------------------------------------------------------


def _build_adjacency(
    graph: ProcessGraph,
) -> dict[UUID, list[tuple[UUID, int]]]:
    """按连线出现顺序构造邻接表。"""

    adjacency: dict[UUID, list[tuple[UUID, int]]] = defaultdict(list)

    for connection in graph.connections:
        # 还没接目标的连线条不构成"走得到"，出边和可达性都只统计接了目标的
        if connection.target_node_id is None:
            continue
        adjacency[connection.source_node_id].append(
            (connection.target_node_id, connection.order_index)
        )
    return adjacency


def _collect_reachable(
    adjacency: Mapping[UUID, list[tuple[UUID, int]]],
    start_node_id: UUID,
) -> set[UUID]:
    """从开始节点出发收集全部可达节点。"""

    reachable: set[UUID] = {start_node_id}
    pending: list[UUID] = [start_node_id]

    while pending:
        current_node_id = pending.pop()
        for target_node_id, _ in adjacency.get(current_node_id, ()):
            if target_node_id in reachable:
                continue
            reachable.add(target_node_id)
            pending.append(target_node_id)

    return reachable


def _find_cycles(
    adjacency: Mapping[UUID, list[tuple[UUID, int]]],
    ordered_node_ids: Sequence[UUID],
) -> list[tuple[UUID, ...]]:
    """用三色标记找出全部环。

    必须与可达性分开计算：不可达分量里的环同样要报出来，用一张颜色表同时表达
    可达性和是否有环会漏掉这部分。
    """

    colors: dict[UUID, int] = {node_id: _COLOR_WHITE for node_id in ordered_node_ids}
    cycles: list[tuple[UUID, ...]] = []
    seen_cycles: set[frozenset[UUID]] = set()

    for root_node_id in ordered_node_ids:
        if colors[root_node_id] != _COLOR_WHITE:
            continue

        colors[root_node_id] = _COLOR_GRAY
        path: list[UUID] = [root_node_id]
        stack: list[tuple[UUID, Any]] = [
            (root_node_id, iter(adjacency.get(root_node_id, ())))
        ]

        while stack:
            current_node_id, iterator = stack[-1]
            advanced = False

            for target_node_id, _ in iterator:
                # 目标不在当前流程内时由连线终点校验负责报错。
                if target_node_id not in colors:
                    continue

                if colors[target_node_id] == _COLOR_WHITE:
                    colors[target_node_id] = _COLOR_GRAY
                    path.append(target_node_id)
                    stack.append(
                        (target_node_id, iter(adjacency.get(target_node_id, ())))
                    )
                    advanced = True
                    break

                if colors[target_node_id] == _COLOR_GRAY:
                    cycle_node_ids = tuple(path[path.index(target_node_id):])
                    cycle_key = frozenset(cycle_node_ids)
                    if cycle_key not in seen_cycles:
                        seen_cycles.add(cycle_key)
                        cycles.append(cycle_node_ids)

            if not advanced:
                stack.pop()
                path.pop()
                colors[current_node_id] = _COLOR_BLACK

    return cycles


# ---------------------------------------------------------------------------
# 复制流程使用的编排重映射
# ---------------------------------------------------------------------------


def serialize_connections(
    connections: Sequence[GraphConnection],
    node_id_map: Mapping[UUID, UUID] | None = None,
) -> dict[str, Any]:
    """把校验过的连线序列化成编排 JSON。

    只写出流程编排认识的结构，避免前端传入的额外键被原样存库后在运行时造成
    不一致。传入节点 ID 映射时同时重写连线两端的节点 ID，供复制流程使用。
    """

    serialized_connections: list[dict[str, Any]] = []
    for connection in connections:
        source_node_id = connection.source_node_id
        target_node_id = connection.target_node_id

        if node_id_map is not None:
            source_node_id = _require_mapped_node(source_node_id, node_id_map)
            if target_node_id is not None:
                target_node_id = _require_mapped_node(target_node_id, node_id_map)

        serialized_connection: dict[str, Any] = {
            "source_node_id": str(source_node_id),
            "target_node_id": str(target_node_id) if target_node_id is not None else None,
        }
        if connection.condition is not None:
            serialized_connection["condition"] = deepcopy(dict(connection.condition))
        serialized_connections.append(serialized_connection)

    return {ORCHESTRATION_CONNECTIONS_KEY: serialized_connections}


def _require_mapped_node(
    node_id: UUID,
    node_id_map: Mapping[UUID, UUID],
) -> UUID:
    """按映射取回新节点 ID，缺失说明编排引用了不属于该流程的节点。"""

    mapped_node_id = node_id_map.get(node_id)
    if mapped_node_id is None:
        raise ProcessValidationError(
            f"源流程的编排引用了不属于该流程的节点：{node_id}"
        )
    return mapped_node_id


def remap_orchestration(
    orchestration: Any,
    node_id_map: Mapping[UUID, UUID],
) -> dict[str, Any]:
    """按节点 ID 映射重建编排数据，供复制流程使用。

    源流程编排结构损坏或引用了不属于该流程的节点时抛出校验异常，避免把脏数据
    复制成两份。
    """

    connections, issues = parse_connections(orchestration)
    if issues:
        raise ProcessValidationError("源流程的编排数据不完整，无法复制", issues)

    return serialize_connections(connections, node_id_map)


def _parse_uuid(raw_value: Any) -> UUID | None:
    """把字符串形式的 UUID 解析成 UUID 对象，失败时返回 None。"""

    if isinstance(raw_value, UUID):
        return raw_value
    if not isinstance(raw_value, str):
        return None
    try:
        return UUID(raw_value)
    except ValueError:
        return None
