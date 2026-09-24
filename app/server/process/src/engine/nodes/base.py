"""节点处理器的公共契约：运行期上下文与处理器协议。

一种节点类型一个文件，各自实现 ``handle``；类型与实现的对应关系集中在
``nodes/registry.py``。这里只放所有处理器共用的东西，不引用任何具体处理器。
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from sqlmodel import Session

from app.server.process.src.engine.graph import VersionGraph
from app.server.process.src.models.approval_model import (
    ApprovalInstance,
    ApprovalNodeExecution,
)
from app.server.process.src.models.process_model import ApprovalProcessVersionNode

if TYPE_CHECKING:  # 只为类型注解：引擎要引用处理器，这里再引用引擎就成环了
    from app.server.process.src.engine.runner import ApprovalEngine


@dataclass(frozen=True)
class NodeContext:
    """节点处理器需要的全部运行期上下文。"""

    engine: "ApprovalEngine"
    instance: ApprovalInstance
    graph: VersionGraph
    execution: ApprovalNodeExecution
    node: ApprovalProcessVersionNode
    db: Session


class NodeHandler(Protocol):
    """节点处理器：进入节点后决定流程继续推进还是等待。"""

    def handle(self, context: NodeContext) -> UUID | None:
        """返回继续推进的节点 ID，返回 None 表示流程在此停下等待。"""
