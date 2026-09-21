"""节点能力定义管理接口。"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.common.schemas.result import Result
from app.common.security import verify_admin_key
from app.server.process.src.schemas.node_definition_schema import (
    NodeDefinitionCreateRequest,
    NodeDefinitionResponse,
    NodeDefinitionUpdateRequest,
)
from app.server.process.src.service.exceptions import (
    NodeDefinitionNotFoundError,
    ProcessConflictError,
)
from app.server.process.src.service.node_definition_service import (
    NodeDefinitionService,
)


router = APIRouter()
node_definition_service = NodeDefinitionService()


def raise_node_definition_http_error(exc: Exception) -> None:
    """将节点定义领域异常转换为明确的 HTTP 异常。"""

    if isinstance(exc, NodeDefinitionNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, ProcessConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    raise exc


@router.post(
    "/admin/node-definitions",
    response_model=Result[NodeDefinitionResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_key)],
    summary="创建节点能力定义",
)
def create_node_definition(
    request: NodeDefinitionCreateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[NodeDefinitionResponse]:
    """注册一种系统支持的节点能力，供流程设计器拖入画布。"""

    try:
        definition = node_definition_service.create_definition(request, db)
        return Result.success(NodeDefinitionResponse.model_validate(definition))
    except ProcessConflictError as exc:
        raise_node_definition_http_error(exc)


@router.get(
    "/admin/node-definitions",
    response_model=Result[list[NodeDefinitionResponse]],
    dependencies=[Depends(verify_admin_key)],
    summary="查询节点能力定义列表",
)
def list_node_definitions(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_postgres_engine),
) -> Result[list[NodeDefinitionResponse]]:
    """分页查询节点能力定义，供流程设计器左侧节点面板使用。"""

    definitions = node_definition_service.list_definitions(db, offset=offset, limit=limit)
    return Result.success(
        [NodeDefinitionResponse.model_validate(definition) for definition in definitions]
    )


@router.get(
    "/admin/node-definitions/{node_definition_id}",
    response_model=Result[NodeDefinitionResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="查询节点能力定义详情",
)
def get_node_definition(
    node_definition_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[NodeDefinitionResponse]:
    """按主键查询节点能力定义。"""

    try:
        definition = node_definition_service.get_definition(node_definition_id, db)
        return Result.success(NodeDefinitionResponse.model_validate(definition))
    except NodeDefinitionNotFoundError as exc:
        raise_node_definition_http_error(exc)


@router.patch(
    "/admin/node-definitions/{node_definition_id}",
    response_model=Result[NodeDefinitionResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="更新节点能力定义",
)
def update_node_definition(
    node_definition_id: UUID,
    request: NodeDefinitionUpdateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[NodeDefinitionResponse]:
    """更新节点定义的名称、说明、图标、配置 Schema 或启停状态。

    node_type 不可修改，需要改变后端执行类型时应新增一条节点定义。
    """

    try:
        definition = node_definition_service.update_definition(
            node_definition_id,
            request,
            db,
        )
        return Result.success(NodeDefinitionResponse.model_validate(definition))
    except (NodeDefinitionNotFoundError, ProcessConflictError) as exc:
        raise_node_definition_http_error(exc)
