"""审批流定义模块领域异常。"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.server.process.src.service.process_validation import ValidationIssue


class ProcessServiceError(Exception):
    """审批流定义模块业务异常基类。"""


class ProcessNotFoundError(ProcessServiceError):
    """指定流程不存在。"""


class NodeDefinitionNotFoundError(ProcessServiceError):
    """指定节点能力定义不存在。"""


class ProcessConflictError(ProcessServiceError):
    """流程、节点或节点定义发生唯一性冲突。"""


class ProcessStateError(ProcessServiceError):
    """当前流程状态不允许执行该操作。"""


class ProcessValidationError(ProcessServiceError):
    """流程结构、配置或引用校验未通过。

    issues 保存全部校验问题，接口层会连同 message 一起返回，便于管理页面一次性
    定位到具体节点、字段或连线。
    """

    def __init__(self, message: str, issues: list["ValidationIssue"] | None = None):
        """保存可读错误信息和结构化校验问题列表。"""

        super().__init__(message)
        self.issues: list["ValidationIssue"] = issues or []
