"""审批流定义模块数据访问层。"""

from app.server.process.src.repository.node_definition_repository import (
    NodeDefinitionRepository,
)
from app.server.process.src.repository.process_repository import ProcessRepository

__all__ = ["NodeDefinitionRepository", "ProcessRepository"]
