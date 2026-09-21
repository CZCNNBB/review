"""审批流定义模块请求与响应模型。"""

from app.server.process.src.schemas.node_definition_schema import (
    NodeDefinitionCreateRequest,
    NodeDefinitionResponse,
    NodeDefinitionUpdateRequest,
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
    "NodeDefinitionCreateRequest",
    "NodeDefinitionResponse",
    "NodeDefinitionUpdateRequest",
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
