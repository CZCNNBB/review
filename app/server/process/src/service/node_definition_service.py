"""节点能力定义查询。

只读：节点类型跟着代码走，清单在 ``src/node_catalog.py``；``process.node_definition``
是应用启动时同步进来的副本，管理端不维护它（见 ``service/node_definition_sync.py``）。
"""

from uuid import UUID

from sqlmodel import Session

from app.server.process.src.models.process_model import NodeDefinition
from app.server.process.src.repository.node_definition_repository import (
    NodeDefinitionRepository,
)
from app.server.process.src.service.exceptions import NodeDefinitionNotFoundError


class NodeDefinitionService:
    """提供节点能力定义的查询能力。"""

    def __init__(self, repository: NodeDefinitionRepository | None = None):
        """初始化节点能力定义服务并允许测试注入 Repository。"""

        self.repository = repository or NodeDefinitionRepository()

    def list_definitions(
        self,
        db: Session,
        offset: int = 0,
        limit: int = 100,
    ) -> list[NodeDefinition]:
        """分页查询节点能力定义。"""

        return self.repository.list_definitions(db, offset=offset, limit=limit)

    def get_definition(
        self,
        node_definition_id: UUID,
        db: Session,
    ) -> NodeDefinition:
        """查询节点能力定义，不存在时抛出领域异常。"""

        definition = self.repository.get_by_id(node_definition_id, db)
        if not definition:
            raise NodeDefinitionNotFoundError("节点定义不存在")
        return definition
