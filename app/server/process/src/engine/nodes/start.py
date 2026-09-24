"""开始节点：流程入口，进入即完成。"""

from uuid import UUID

from app.server.process.src.engine.nodes.base import NodeContext


class StartNodeHandler:
    """开始节点不产生人工任务，进入后立即完成并按编排选择后续节点。"""

    def handle(self, context: NodeContext) -> UUID | None:
        """完成开始节点并返回按编排选出的后续节点。"""

        return context.engine.complete_node(
            context.instance,
            context.graph,
            context.execution,
            context.db,
        )
