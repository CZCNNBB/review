"""节点能力定义查询接口。

只读：节点类型跟着代码走，清单在 ``src/node_catalog.py``，应用启动时由
``service/node_definition_sync.py`` 同步进库。管理端改这里没有意义（下次启动会被改回），
所以不提供增改接口 —— 要加类型得后端加处理器与清单条目。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.common.schemas.result import Result
from app.common.security import verify_admin_key
from app.server.process.src.schemas.node_definition_schema import (
    NodeDefinitionResponse,
)
from app.server.process.src.service.exceptions import NodeDefinitionNotFoundError
from app.server.process.src.service.node_definition_service import (
    NodeDefinitionService,
)


router = APIRouter()
node_definition_service = NodeDefinitionService()


def raise_node_definition_http_error(exc: Exception) -> None:
    """将节点定义领域异常转换为明确的 HTTP 异常。"""

    if isinstance(exc, NodeDefinitionNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    raise exc


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
