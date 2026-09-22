"""业务接入模块的枚举取值、调用规则和校验规则码。"""

# ---------------------------------------------------------------------------
# 业务动作状态
# ---------------------------------------------------------------------------

ACTION_STATUS_ENABLED = "ENABLED"
ACTION_STATUS_DISABLED = "DISABLED"

ACTION_STATUSES = (ACTION_STATUS_ENABLED, ACTION_STATUS_DISABLED)
ACTION_STATUS_PATTERN = r"^(ENABLED|DISABLED)$"

# ---------------------------------------------------------------------------
# 业务动作标识
# ---------------------------------------------------------------------------

ACTION_CODE_PATTERN = r"^[A-Za-z][A-Za-z0-9_]*$"

# ---------------------------------------------------------------------------
# 调用配置
# ---------------------------------------------------------------------------

# 第一版只允许固定方法，业务发起请求不能动态指定方法和地址。
SUPPORTED_HTTP_METHODS = ("POST", "PUT", "PATCH")

# 成功状态码数组为空时表示全部 2xx，由 callback 模块按此约定判断调用结果。
DEFAULT_SUCCESS_STATUS_CODES: tuple[int, ...] = ()

DEFAULT_TIMEOUT_MS = 5000
MIN_TIMEOUT_MS = 1
MAX_TIMEOUT_MS = 300000

# 相对路径必须以单个斜杠开头，且不能保存完整 URL 或协议相对地址。
RELATIVE_PATH_PREFIX = "/"
RELATIVE_PATH_FORBIDDEN_PREFIX = "//"
FULL_URL_MARKER = "://"

# ---------------------------------------------------------------------------
# 校验规则码
# ---------------------------------------------------------------------------

# 执行参数不符合业务动作的请求 Schema 时使用，错误信息带具体字段路径。
RULE_EXECUTION_PAYLOAD_INVALID = "EXECUTION_PAYLOAD_INVALID"
