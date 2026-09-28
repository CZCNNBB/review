"""抄送节点：生成只读抄送记录后立即推进流程。"""

from uuid import UUID

from app.server.process.src.engine.nodes.base import NodeContext
from app.server.process.src.service.exceptions import ProcessStateError


class CopyNodeHandler:
    """把审批单放进收件人的抄送列表，不创建审批待办。"""

    def handle(self, context: NodeContext) -> UUID | None:
        """写入收件人记录并完成当前节点，返回下一节点 ID。"""

        recipient_ids = context.engine.resolve_copy_recipient_person_ids(context.node)
        if not recipient_ids:
            raise ProcessStateError(
                f"节点「{context.node.name}」没有有效的抄送人，无法继续流程"
            )

        context.engine.create_copy_records(
            context.instance,
            context.execution,
            recipient_ids,
            context.db,
        )
        context.execution.result_json = {
            **context.execution.result_json,
            "recipient_person_ids": [str(person_id) for person_id in recipient_ids],
        }
        return context.engine.complete_node(
            context.instance,
            context.graph,
            context.execution,
            context.db,
        )
