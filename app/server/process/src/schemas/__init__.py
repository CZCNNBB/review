"""审批流定义模块请求与响应模型。"""

from app.server.process.src.schemas.node_definition_schema import (
    NodeDefinitionResponse,
)
from app.server.process.src.schemas.process_schema import (
    ProcessCreateRequest,
    ProcessGraphNodeRequest,
    ProcessGraphNodeResponse,
    ProcessGraphResponse,
    ProcessGraphSaveRequest,
    ProcessResponse,
    ProcessValidationIssueResponse,
    ProcessValidationResponse,
    ProcessVersionResponse,
)

__all__ = [
    "NodeDefinitionResponse",
    "ProcessCreateRequest",
    "ProcessGraphNodeRequest",
    "ProcessGraphNodeResponse",
    "ProcessGraphResponse",
    "ProcessGraphSaveRequest",
    "ProcessResponse",
    "ProcessValidationIssueResponse",
    "ProcessValidationResponse",
    "ProcessVersionResponse",
]
