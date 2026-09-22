"""业务接入模块领域异常。"""

from app.server.process.src.service.process_validation import ValidationIssue


class BusinessAccessError(Exception):
    """业务接入模块业务异常基类。"""


class BusinessActionNotFoundError(BusinessAccessError):
    """业务动作不存在。"""


class BusinessActionConflictError(BusinessAccessError):
    """业务动作标识发生唯一性冲突。"""


class BusinessActionStateError(BusinessAccessError):
    """业务动作状态不允许当前操作，例如动作已经停用。"""


class BusinessActionValidationError(BusinessAccessError):
    """业务动作配置或执行参数校验未通过。

    错误结构复用审批模块的 ValidationIssue，让 422 响应在业务动作管理和发起审批
    两个接口中保持同一种可以定位到字段的问题列表。
    """

    def __init__(self, message: str, issues: list[ValidationIssue] | None = None):
        """保存校验失败原因和结构化的字段问题列表。"""

        super().__init__(message)
        self.issues = list(issues or ())
