"""条件分支节点：进入即按出线条件选择后续节点。"""

from uuid import UUID

from app.server.process.src.engine.nodes.base import NodeContext


class ConditionNodeHandler:
    """条件分支节点不产生人工任务，进入后立即按出线条件选择后续节点。

    和开始节点一样是"进入即离开"，区别只在语义：开始节点是流程入口，条件分支节点
    用来把一条路拆成多条。分支条件和默认路径都保存在版本编排里，这里不读节点配置。
    """

    def handle(self, context: NodeContext) -> UUID | None:
        """按编排条件选择后续节点。"""

        return context.engine.complete_node(
            context.instance,
            context.graph,
            context.execution,
            context.db,
        )
