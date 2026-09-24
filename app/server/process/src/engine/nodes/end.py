"""结束节点：流程正常走完，进入即把实例置为"审批通过"。"""

from uuid import UUID

from app.server.process.src.engine.nodes.base import NodeContext


class EndNodeHandler:
    """结束节点表示流程正常走完：进入即把实例置为"审批通过"。

    节点本身没有配置项。审批被拒绝由审批人在人工审批节点当场结束实例（见
    ``reject_instance``），根本走不到结束节点，所以这里不存在"拒绝出口"。
    """

    def handle(self, context: NodeContext) -> UUID | None:
        """以审批通过结束实例。"""

        context.engine.finish_instance(context.instance, context.execution, context.db)
        return None
