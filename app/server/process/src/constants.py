"""审批流定义模块的枚举取值、条件操作符规则和校验规则码。"""

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# 节点后端执行类型
# ---------------------------------------------------------------------------

NODE_TYPE_START = "START"
NODE_TYPE_APPROVAL = "APPROVAL"
NODE_TYPE_END = "END"

# 后端已经实现执行器的节点类型。新增节点定义时 node_type 必须落在这个集合内。
SUPPORTED_NODE_TYPES = frozenset({NODE_TYPE_START, NODE_TYPE_APPROVAL, NODE_TYPE_END})
NODE_TYPE_PATTERN = r"^(START|APPROVAL|END)$"

# 节点定义保存的是能力元数据，node_type 仅表示后端执行分类，不承担唯一标识作用。
NODE_DEFINITION_STATUS_ENABLED = "ENABLED"
NODE_DEFINITION_STATUS_DISABLED = "DISABLED"
NODE_DEFINITION_STATUS_PATTERN = r"^(ENABLED|DISABLED)$"

# ---------------------------------------------------------------------------
# 流程状态
# ---------------------------------------------------------------------------

PROCESS_STATUS_DRAFT = "DRAFT"
PROCESS_STATUS_ENABLED = "ENABLED"
PROCESS_STATUS_DISABLED = "DISABLED"

# 复制流程时追加的名称后缀。base 按此长度截断，保证加后缀后不超过 name 字段的 128 字符。
PROCESS_COPY_NAME_SUFFIX = "（副本）"
PROCESS_NAME_MAX_LENGTH = 128
PROCESS_COPY_NAME_BASE_MAX_LENGTH = (
    PROCESS_NAME_MAX_LENGTH - len(PROCESS_COPY_NAME_SUFFIX)
)

# ---------------------------------------------------------------------------
# 多人审批规则
# ---------------------------------------------------------------------------

APPROVAL_MODE_AND = "AND"
APPROVAL_MODE_OR = "OR"
APPROVAL_MODES = (APPROVAL_MODE_AND, APPROVAL_MODE_OR)
APPROVAL_MODE_PATTERN = r"^(AND|OR)$"

# 结束节点允许的结果状态。第一版只支持审批通过和审批拒绝两种出口。
END_RESULT_STATUS_APPROVED = "APPROVED"
END_RESULT_STATUS_REJECTED = "REJECTED"
END_RESULT_STATUSES = (END_RESULT_STATUS_APPROVED, END_RESULT_STATUS_REJECTED)

# ---------------------------------------------------------------------------
# 编排与条件表达式
# ---------------------------------------------------------------------------

# 条件字段路径统一使用 approval_form 前缀，指向审批表单 Schema 中的字段。
FORM_FIELD_PREFIX = "approval_form."

ORCHESTRATION_CONNECTIONS_KEY = "connections"


@dataclass(frozen=True)
class OperatorRule:
    """描述一个条件操作符对取值的要求。"""

    requires_value: bool
    value_must_be_array: bool
    supports_ordering: bool


# 第一版只支持结构化 JSON 条件，不允许执行 Python、JavaScript 或 SQL。
CONDITION_OPERATOR_RULES: dict[str, OperatorRule] = {
    "EQ": OperatorRule(requires_value=True, value_must_be_array=False, supports_ordering=False),
    "NE": OperatorRule(requires_value=True, value_must_be_array=False, supports_ordering=False),
    "GT": OperatorRule(requires_value=True, value_must_be_array=False, supports_ordering=True),
    "GTE": OperatorRule(requires_value=True, value_must_be_array=False, supports_ordering=True),
    "LT": OperatorRule(requires_value=True, value_must_be_array=False, supports_ordering=True),
    "LTE": OperatorRule(requires_value=True, value_must_be_array=False, supports_ordering=True),
    "IN": OperatorRule(requires_value=True, value_must_be_array=True, supports_ordering=False),
    "NOT_IN": OperatorRule(requires_value=True, value_must_be_array=True, supports_ordering=False),
    "IS_EMPTY": OperatorRule(requires_value=False, value_must_be_array=False, supports_ordering=False),
    "NOT_EMPTY": OperatorRule(requires_value=False, value_must_be_array=False, supports_ordering=False),
}

# 可以做大小比较的字符串格式。其余字符串只能做相等判断。
ORDERABLE_STRING_FORMATS = frozenset({"date", "date-time", "time"})
ORDERABLE_TYPES = frozenset({"number", "integer"})
NUMERIC_TYPES = frozenset({"number", "integer"})

# 展开表单 Schema 时的最大下钻深度，用于防御自引用结构。
MAX_FORM_SCHEMA_DEPTH = 5

# 单个节点的配置结构错误最多返回多少条，超出部分折叠成一条提示。
MAX_CONFIG_ISSUES_PER_NODE = 10

# ---------------------------------------------------------------------------
# 校验规则码
# 前端可以按 code 定位到画布上的具体节点、字段或连线。
# ---------------------------------------------------------------------------

RULE_ORCHESTRATION_INVALID = "ORCHESTRATION_INVALID"

RULE_NODE_DEFINITION_NOT_FOUND = "NODE_DEFINITION_NOT_FOUND"
RULE_NODE_DEFINITION_DISABLED = "NODE_DEFINITION_DISABLED"
RULE_NODE_TYPE_UNSUPPORTED = "NODE_TYPE_UNSUPPORTED"
RULE_NODE_CONFIG_INVALID = "NODE_CONFIG_INVALID"

RULE_APPROVAL_MODE_INVALID = "APPROVAL_MODE_INVALID"
RULE_APPROVER_REQUIRED = "APPROVER_REQUIRED"
RULE_APPROVER_ID_INVALID = "APPROVER_ID_INVALID"
RULE_APPROVER_DUPLICATE = "APPROVER_DUPLICATE"
RULE_APPROVER_NOT_FOUND = "APPROVER_NOT_FOUND"
RULE_APPROVER_DISABLED = "APPROVER_DISABLED"

RULE_START_COUNT_INVALID = "START_COUNT_INVALID"
RULE_END_REQUIRED = "END_REQUIRED"
RULE_END_APPROVED_REQUIRED = "END_APPROVED_REQUIRED"
RULE_END_RESULT_STATUS_INVALID = "END_RESULT_STATUS_INVALID"

RULE_CONNECTION_NODE_UNKNOWN = "CONNECTION_NODE_UNKNOWN"
RULE_START_AS_TARGET = "START_AS_TARGET"
RULE_END_AS_SOURCE = "END_AS_SOURCE"

RULE_NODE_UNREACHABLE = "NODE_UNREACHABLE"
RULE_NODE_WITHOUT_OUTGOING = "NODE_WITHOUT_OUTGOING"
RULE_GRAPH_CYCLE = "GRAPH_CYCLE"

RULE_CONNECTION_CONDITION_REQUIRED = "CONNECTION_CONDITION_REQUIRED"
RULE_CONNECTION_DEFAULT_REQUIRED = "CONNECTION_DEFAULT_REQUIRED"
RULE_CONNECTION_DEFAULT_DUPLICATE = "CONNECTION_DEFAULT_DUPLICATE"
RULE_CONNECTION_DEFAULT_WITH_CONDITION = "CONNECTION_DEFAULT_WITH_CONDITION"
RULE_CONNECTION_CONDITION_INVALID = "CONNECTION_CONDITION_INVALID"
RULE_CONNECTION_FIELD_UNKNOWN = "CONNECTION_FIELD_UNKNOWN"
RULE_CONNECTION_OPERATOR_INCOMPATIBLE = "CONNECTION_OPERATOR_INCOMPATIBLE"
RULE_CONNECTION_VALUE_NOT_IN_ENUM = "CONNECTION_VALUE_NOT_IN_ENUM"

# 节点 ID 被其他流程占用时使用的冲突提示，在 Service 层作为领域冲突返回。
NODE_ID_OCCUPIED_MESSAGE = "节点 ID 已被其他流程占用，请刷新画布后重试"
