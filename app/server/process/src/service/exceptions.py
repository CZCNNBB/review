"""审批流定义与运行模块领域异常。

审批运行的异常继承对应的定义模块异常，接口层可以共用同一套错误映射，只有“操作人
不是任务处理人”需要单独返回 403。
"""

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


class ApprovalNotFoundError(ProcessNotFoundError):
    """指定审批实例、节点执行或审批任务不存在。"""


class ApprovalStateError(ProcessStateError):
    """当前审批状态不允许执行该操作，例如实例已结束或任务已被处理。"""


class ApprovalConflictError(ProcessConflictError):
    """并发审批操作冲突，需要重新读取当前状态后重试。"""


class ApprovalPermissionError(ProcessServiceError):
    """当前操作人不是该审批任务的处理人。"""
