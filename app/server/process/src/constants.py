"""审批流定义模块的枚举取值、条件操作符规则和校验规则码。"""

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# 节点后端执行类型
# ---------------------------------------------------------------------------

NODE_TYPE_START = "START"
NODE_TYPE_APPROVAL = "APPROVAL"
NODE_TYPE_CONDITION = "CONDITION"
NODE_TYPE_END = "END"

# 节点类型的清单不在这里：处理器在 engine/nodes/，声明（名字、图标、配置 Schema，
# 以及库里那一行的固定 id）在 src/node_catalog.py，白名单 SUPPORTED_NODE_TYPES 由清单派生。
# 这里只保留类型名常量，供各处理器引用。
#   新增一种节点类型 = 新建 engine/nodes/<类型>.py + 在 registry 加一行 + 在清单加一条。

# 分支只允许从条件分支节点出去，其余节点的出线数量上限见 RULE_TOO_MANY_OUTGOING_CONNECTIONS。
BRANCHING_NODE_TYPES = frozenset({NODE_TYPE_CONDITION})

# 节点定义行的状态。定义由代码清单在启动时同步写入，一类一行（见 node_definition_sync）。
NODE_DEFINITION_STATUS_ENABLED = "ENABLED"
NODE_DEFINITION_STATUS_DISABLED = "DISABLED"

# ---------------------------------------------------------------------------
# 流程状态
# ---------------------------------------------------------------------------

PROCESS_STATUS_DRAFT = "DRAFT"
PROCESS_STATUS_ENABLED = "ENABLED"
PROCESS_STATUS_DISABLED = "DISABLED"

# 流程版本只有草稿和已发布两种状态。已发布版本在 Service 层永久只读。
PROCESS_VERSION_STATUS_DRAFT = "DRAFT"
PROCESS_VERSION_STATUS_PUBLISHED = "PUBLISHED"

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

RULE_CONNECTION_NODE_UNKNOWN = "CONNECTION_NODE_UNKNOWN"
RULE_START_AS_TARGET = "START_AS_TARGET"
RULE_END_AS_SOURCE = "END_AS_SOURCE"

RULE_NODE_UNREACHABLE = "NODE_UNREACHABLE"
RULE_NODE_WITHOUT_OUTGOING = "NODE_WITHOUT_OUTGOING"
RULE_TOO_MANY_OUTGOING_CONNECTIONS = "TOO_MANY_OUTGOING_CONNECTIONS"
RULE_GRAPH_CYCLE = "GRAPH_CYCLE"

# 条件分支节点的出线按顺序组成 if/elif/else 阶梯：前面每条都要有条件，最后一条是
# "其余情况"不能带条件。分支的兜底由位置表达，不再使用单独的标志位。
RULE_BRANCH_MISSING_CONDITION = "BRANCH_MISSING_CONDITION"
RULE_BRANCH_FALLBACK_INVALID = "BRANCH_FALLBACK_INVALID"
# 分支可以在节点里先定义、之后再拉线到目标，发布前必须把去向补齐。
RULE_BRANCH_TARGET_REQUIRED = "BRANCH_TARGET_REQUIRED"
RULE_CONNECTION_CONDITION_INVALID = "CONNECTION_CONDITION_INVALID"
RULE_CONNECTION_FIELD_UNKNOWN = "CONNECTION_FIELD_UNKNOWN"
RULE_CONNECTION_OPERATOR_INCOMPATIBLE = "CONNECTION_OPERATOR_INCOMPATIBLE"
RULE_CONNECTION_VALUE_NOT_IN_ENUM = "CONNECTION_VALUE_NOT_IN_ENUM"

# 节点 ID 被其他流程占用时使用的冲突提示，在 Service 层作为领域冲突返回。
NODE_ID_OCCUPIED_MESSAGE = "节点 ID 已被其他流程占用，请刷新画布后重试"

# ---------------------------------------------------------------------------
# 审批运行状态
# ---------------------------------------------------------------------------

# 审批实例状态。只有 RUNNING 的实例可以继续推进，其余状态都是终态。
INSTANCE_STATUS_RUNNING = "RUNNING"
INSTANCE_STATUS_APPROVED = "APPROVED"
INSTANCE_STATUS_REJECTED = "REJECTED"
INSTANCE_STATUS_CANCELLED = "CANCELLED"
INSTANCE_STATUS_ERROR = "ERROR"

INSTANCE_STATUSES = (
    INSTANCE_STATUS_RUNNING,
    INSTANCE_STATUS_APPROVED,
    INSTANCE_STATUS_REJECTED,
    INSTANCE_STATUS_CANCELLED,
    INSTANCE_STATUS_ERROR,
)

# 终态实例不再接受审批操作，实例耗时改用 finished_at 计算。
INSTANCE_FINISHED_STATUSES = frozenset(
    {
        INSTANCE_STATUS_APPROVED,
        INSTANCE_STATUS_REJECTED,
        INSTANCE_STATUS_CANCELLED,
        INSTANCE_STATUS_ERROR,
    }
)

# 节点执行状态。ACTIVE 表示实例当前停留的节点，同一实例最多只有一条。
NODE_EXECUTION_STATUS_ACTIVE = "ACTIVE"
NODE_EXECUTION_STATUS_COMPLETED = "COMPLETED"
NODE_EXECUTION_STATUS_REJECTED = "REJECTED"
NODE_EXECUTION_STATUS_CANCELLED = "CANCELLED"
NODE_EXECUTION_STATUS_ERROR = "ERROR"

NODE_EXECUTION_STATUSES = (
    NODE_EXECUTION_STATUS_ACTIVE,
    NODE_EXECUTION_STATUS_COMPLETED,
    NODE_EXECUTION_STATUS_REJECTED,
    NODE_EXECUTION_STATUS_CANCELLED,
    NODE_EXECUTION_STATUS_ERROR,
)

# 节点执行状态到实例终态的映射，节点因拒绝结束时同步结束整个实例。
NODE_EXECUTION_TERMINAL_STATUSES = frozenset(
    {
        NODE_EXECUTION_STATUS_COMPLETED,
        NODE_EXECUTION_STATUS_REJECTED,
        NODE_EXECUTION_STATUS_CANCELLED,
        NODE_EXECUTION_STATUS_ERROR,
    }
)

# 审批任务状态。PENDING 是被取消的唯一来源状态。
TASK_STATUS_PENDING = "PENDING"
TASK_STATUS_APPROVED = "APPROVED"
TASK_STATUS_REJECTED = "REJECTED"
TASK_STATUS_CANCELLED = "CANCELLED"

TASK_STATUSES = (
    TASK_STATUS_PENDING,
    TASK_STATUS_APPROVED,
    TASK_STATUS_REJECTED,
    TASK_STATUS_CANCELLED,
)

TASK_HANDLED_STATUSES = frozenset({TASK_STATUS_APPROVED, TASK_STATUS_REJECTED})

# 审批记录动作，必须与任务终态一一对应。
RECORD_ACTION_APPROVE = "APPROVE"
RECORD_ACTION_REJECT = "REJECT"

RECORD_ACTIONS = (RECORD_ACTION_APPROVE, RECORD_ACTION_REJECT)

# 审批操作到任务状态的映射。
TASK_STATUS_BY_ACTION = {
    RECORD_ACTION_APPROVE: TASK_STATUS_APPROVED,
    RECORD_ACTION_REJECT: TASK_STATUS_REJECTED,
}

# 单次发起或审批最多推进的节点数量。编排已经禁止成环，这里的上限用于防御
# 编排数据异常时把请求拖死在循环里。
MAX_ADVANCE_STEPS = 100

# 运行期校验规则码。发起审批时的表单校验结果沿用定义模块的问题结构。
RULE_APPROVAL_FORM_INVALID = "APPROVAL_FORM_INVALID"
RULE_APPLICANT_INVALID = "APPLICANT_INVALID"

# 当前节点在选择后续路径时找不到任何可走的连线，属于编排数据损坏。
RULE_ENGINE_PATH_NOT_FOUND = "ENGINE_PATH_NOT_FOUND"

# ---------------------------------------------------------------------------
# 业务执行
# ---------------------------------------------------------------------------

# 业务执行状态。第一版没有多次重试，因此一条记录既表示待执行任务，也表示唯一一次调用结果。
EXECUTION_STATUS_PENDING = "PENDING"
EXECUTION_STATUS_RUNNING = "RUNNING"
EXECUTION_STATUS_SUCCEEDED = "SUCCEEDED"
EXECUTION_STATUS_FAILED = "FAILED"

EXECUTION_STATUSES = (
    EXECUTION_STATUS_PENDING,
    EXECUTION_STATUS_RUNNING,
    EXECUTION_STATUS_SUCCEEDED,
    EXECUTION_STATUS_FAILED,
)

# 只有 PENDING 记录会被后台执行器领取，其余状态都是终态。
EXECUTION_STATUS_PATTERN = r"^(PENDING|RUNNING|SUCCEEDED|FAILED)$"

# 执行记录保存的字段长度上限。业务系统可能返回很大的正文，落库前必须截断，
# 避免数据库膨胀、日志污染和管理页面加载缓慢。
# 响应正文按 UTF-8 字节数限制，错误摘要按字符数限制（与 error_message 列长度一致）。
MAX_RESPONSE_BODY_BYTES = 8192
MAX_ERROR_MESSAGE_LENGTH = 1000
MAX_REQUEST_URL_LENGTH = 1000

# 执行器写入的失败摘要。租户维度的失败原因由 tenant 模块提供的回调配置实现给出，
# 这里只保留业务动作快照本身缺失时的提示。
EXECUTION_ERROR_ACTION_MISSING = "业务动作配置缺失，无法确定调用方式"

# 后台 Worker 的环境变量名。轮询频率和领取数量不能写死在代码里。
ENV_WORKER_ENABLED = "BUSINESS_EXECUTION_WORKER_ENABLED"
ENV_POLL_INTERVAL_SECONDS = "BUSINESS_EXECUTION_POLL_INTERVAL_SECONDS"
ENV_BATCH_SIZE = "BUSINESS_EXECUTION_BATCH_SIZE"
ENV_CONCURRENCY = "BUSINESS_EXECUTION_CONCURRENCY"

DEFAULT_WORKER_ENABLED = True
DEFAULT_POLL_INTERVAL_SECONDS = 2.0
DEFAULT_BATCH_SIZE = 10
DEFAULT_CONCURRENCY = 5
