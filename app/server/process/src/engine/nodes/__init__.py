"""节点类型：一种类型一个处理器文件，类型清单与注册表都在 ``registry``。

引擎与上层服务都从这里取名字，不直接钻进具体模块，这样以后调整文件划分不影响调用方。
"""

from app.server.process.src.engine.nodes.approval import (
    OUTCOME_APPROVED,
    OUTCOME_PENDING,
    OUTCOME_REJECTED,
    ApprovalNodeHandler,
    resolve_approval_outcome,
)
from app.server.process.src.engine.nodes.base import NodeContext, NodeHandler
from app.server.process.src.engine.nodes.condition import ConditionNodeHandler
from app.server.process.src.engine.nodes.end import EndNodeHandler
from app.server.process.src.engine.nodes.registry import NODE_HANDLERS
from app.server.process.src.engine.nodes.start import StartNodeHandler
from app.server.process.src.node_catalog import (
    NODE_TYPES,
    SUPPORTED_NODE_TYPES,
    NodeTypeSpec,
)

__all__ = [
    "NODE_HANDLERS",
    "NODE_TYPES",
    "OUTCOME_APPROVED",
    "OUTCOME_PENDING",
    "OUTCOME_REJECTED",
    "SUPPORTED_NODE_TYPES",
    "ApprovalNodeHandler",
    "ConditionNodeHandler",
    "EndNodeHandler",
    "NodeContext",
    "NodeHandler",
    "NodeTypeSpec",
    "StartNodeHandler",
    "resolve_approval_outcome",
]
