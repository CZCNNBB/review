"""人工审批节点：为全部审批人创建待办任务，然后停下等人工处理。

节点结果判定（AND / OR 与拒绝优先）也在这里：它只依赖任务状态、不碰数据库，
任务服务在审批动作之后直接调用它。
"""

from typing import Sequence
from uuid import UUID

from app.server.process.src.constants import APPROVAL_MODE_AND, APPROVAL_MODES
from app.server.process.src.engine.nodes.base import NodeContext
from app.server.process.src.service.exceptions import ProcessStateError

# 节点结果判定结论。PENDING 表示还有审批人没有处理，节点结果尚未形成。
OUTCOME_PENDING = "PENDING"
OUTCOME_APPROVED = "APPROVED"
OUTCOME_REJECTED = "REJECTED"


def resolve_approval_outcome(
    approval_mode: str,
    task_statuses: Sequence[str],
) -> str:
    """按审批模式判断人工审批节点是否已经形成结果。

    AND 需要全部任务同意，OR 只取第一个有效结果。两种模式下任意一人拒绝都立即
    拒绝整个审批实例，因此拒绝判断始终优先。
    """

    if any(status == "REJECTED" for status in task_statuses):
        return OUTCOME_REJECTED

    approved_count = sum(1 for status in task_statuses if status == "APPROVED")
    if approval_mode == APPROVAL_MODE_AND:
        if task_statuses and approved_count == len(task_statuses):
            return OUTCOME_APPROVED
        return OUTCOME_PENDING

    # OR 模式下第一个成功提交的同意结果决定节点通过。
    if approved_count > 0:
        return OUTCOME_APPROVED

    return OUTCOME_PENDING


class ApprovalNodeHandler:
    """人工审批节点同时创建全部审批任务，然后等待人工处理。"""

    def handle(self, context: NodeContext) -> UUID | None:
        """创建待办任务并让实例停在当前节点。"""

        approval_mode = context.node.config_json.get("approval_mode")
        if approval_mode not in APPROVAL_MODES:
            raise ProcessStateError(
                f"节点「{context.node.name}」的审批模式无效，无法创建审批任务"
            )

        approver_person_ids = context.engine.resolve_approver_person_ids(context.node)
        if not approver_person_ids:
            raise ProcessStateError(
                f"节点「{context.node.name}」没有有效的审批人，无法创建审批任务"
            )

        context.engine.create_approval_tasks(
            instance=context.instance,
            execution=context.execution,
            approver_person_ids=approver_person_ids,
            db=context.db,
        )
        context.execution.result_json = {
            **context.execution.result_json,
            "approval_mode": approval_mode,
            "approver_person_ids": [str(item) for item in approver_person_ids],
        }
        context.engine.repository.add_node_execution(context.execution, context.db)
        return None
