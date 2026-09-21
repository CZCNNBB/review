"""审批流定义、流程编排和启停管理接口。"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.common.schemas.result import Result
from app.common.security import verify_admin_key
from app.server.process.src.schemas.process_schema import (
    ProcessCreateRequest,
    ProcessGraphNodeResponse,
    ProcessGraphResponse,
    ProcessGraphSaveRequest,
    ProcessResponse,
    ProcessUpdateRequest,
    ProcessValidationIssueResponse,
    ProcessValidationResponse,
)
from app.server.process.src.service.exceptions import (
    ProcessConflictError,
    ProcessNotFoundError,
    ProcessStateError,
    ProcessValidationError,
)
from app.server.process.src.service.process_service import (
    ProcessGraphView,
    ProcessService,
)


router = APIRouter()
process_service = ProcessService()


def raise_process_http_error(exc: Exception) -> None:
    """将审批流领域异常转换为明确的 HTTP 异常。

    校验失败时返回结构化的 issues，管理页面可以据此定位到具体节点、字段或连线。
    """

    if isinstance(exc, ProcessNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, (ProcessConflictError, ProcessStateError)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, ProcessValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": str(exc),
                "issues": [
                    ProcessValidationIssueResponse.model_validate(issue).model_dump(
                        mode="json"
                    )
                    for issue in exc.issues
                ],
            },
        ) from exc
    raise exc


def build_graph_response(graph_view: ProcessGraphView) -> ProcessGraphResponse:
    """把整图读取结果转换成接口响应。"""

    process = graph_view.process
    nodes: list[ProcessGraphNodeResponse] = []
    for node in graph_view.nodes:
        definition = graph_view.definitions.get(node.node_definition_id)
        nodes.append(
            ProcessGraphNodeResponse(
                id=node.id,
                node_definition_id=node.node_definition_id,
                node_type=definition.node_type if definition else None,
                node_definition_name=definition.name if definition else None,
                name=node.name,
                config=node.config_json,
                position=node.position_json,
                created_at=node.created_at,
                updated_at=node.updated_at,
            )
        )

    return ProcessGraphResponse(
        process_id=process.id,
        name=process.name,
        description=process.description,
        status=process.status,
        form_schema=process.form_schema_json,
        form_ui_schema=process.form_ui_schema_json,
        orchestration=process.orchestration_json,
        nodes=nodes,
        created_at=process.created_at,
        updated_at=process.updated_at,
    )


@router.post(
    "/admin/processes",
    response_model=Result[ProcessResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_key)],
    summary="创建审批流",
)
def create_process(
    request: ProcessCreateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[ProcessResponse]:
    """创建审批流，新建流程恒为草稿状态。"""

    process = process_service.create_process(request, db)
    return Result.success(ProcessResponse.build(process, node_count=0))


@router.get(
    "/admin/processes",
    response_model=Result[list[ProcessResponse]],
    dependencies=[Depends(verify_admin_key)],
    summary="查询审批流列表",
)
def list_processes(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_postgres_engine),
) -> Result[list[ProcessResponse]]:
    """分页查询审批流并附带节点数量。"""

    processes = process_service.list_processes(db, offset=offset, limit=limit)
    return Result.success(
        [
            ProcessResponse.build(process, node_count=node_count)
            for process, node_count in processes
        ]
    )


@router.get(
    "/admin/processes/{process_id}",
    response_model=Result[ProcessResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="查询审批流详情",
)
def get_process(
    process_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[ProcessResponse]:
    """按主键查询审批流基本资料。"""

    try:
        process = process_service.get_process(process_id, db)
        node_count = process_service.count_nodes(process_id, db)
        return Result.success(ProcessResponse.build(process, node_count=node_count))
    except ProcessNotFoundError as exc:
        raise_process_http_error(exc)


@router.patch(
    "/admin/processes/{process_id}",
    response_model=Result[ProcessResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="更新审批流",
)
def update_process(
    process_id: UUID,
    request: ProcessUpdateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[ProcessResponse]:
    """更新审批流名称、说明或审批表单。"""

    try:
        process = process_service.update_process(process_id, request, db)
        node_count = process_service.count_nodes(process_id, db)
        return Result.success(ProcessResponse.build(process, node_count=node_count))
    except (
        ProcessNotFoundError,
        ProcessValidationError,
    ) as exc:
        raise_process_http_error(exc)


@router.post(
    "/admin/processes/{process_id}/copy",
    response_model=Result[ProcessResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_key)],
    summary="复制审批流",
)
def copy_process(
    process_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[ProcessResponse]:
    """复制审批流，新流程使用全新节点 ID 并保持草稿状态。"""

    try:
        process = process_service.copy_process(process_id, db)
        node_count = process_service.count_nodes(process.id, db)
        return Result.success(ProcessResponse.build(process, node_count=node_count))
    except (ProcessNotFoundError, ProcessValidationError) as exc:
        raise_process_http_error(exc)


@router.post(
    "/admin/processes/{process_id}/enable",
    response_model=Result[ProcessResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="启用审批流",
)
def enable_process(
    process_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[ProcessResponse]:
    """启用审批流，只有完整性校验通过才允许启用。"""

    try:
        process = process_service.enable_process(process_id, db)
        node_count = process_service.count_nodes(process_id, db)
        return Result.success(ProcessResponse.build(process, node_count=node_count))
    except (ProcessNotFoundError, ProcessValidationError) as exc:
        raise_process_http_error(exc)


@router.post(
    "/admin/processes/{process_id}/disable",
    response_model=Result[ProcessResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="停用审批流",
)
def disable_process(
    process_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[ProcessResponse]:
    """停用审批流，已经停用时直接返回当前状态。"""

    try:
        process = process_service.disable_process(process_id, db)
        node_count = process_service.count_nodes(process_id, db)
        return Result.success(ProcessResponse.build(process, node_count=node_count))
    except (ProcessNotFoundError, ProcessStateError) as exc:
        raise_process_http_error(exc)


@router.get(
    "/admin/processes/{process_id}/graph",
    response_model=Result[ProcessGraphResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="读取流程编排",
)
def get_process_graph(
    process_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[ProcessGraphResponse]:
    """读取流程主体、全部节点实例和完整编排，供流程设计器渲染画布。"""

    try:
        graph_view = process_service.get_graph(process_id, db)
        return Result.success(build_graph_response(graph_view))
    except ProcessNotFoundError as exc:
        raise_process_http_error(exc)


@router.put(
    "/admin/processes/{process_id}/graph",
    response_model=Result[ProcessGraphResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="保存流程编排",
)
def save_process_graph(
    process_id: UUID,
    request: ProcessGraphSaveRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[ProcessGraphResponse]:
    """一次提交完整流程、节点列表和编排关系，失败时整体回滚。"""

    try:
        graph_view = process_service.save_graph(process_id, request, db)
        return Result.success(build_graph_response(graph_view))
    except (
        ProcessNotFoundError,
        ProcessConflictError,
        ProcessValidationError,
    ) as exc:
        raise_process_http_error(exc)


@router.post(
    "/admin/processes/{process_id}/validate",
    response_model=Result[ProcessValidationResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="校验流程完整性",
)
def validate_process(
    process_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[ProcessValidationResponse]:
    """校验流程完整性并返回全部问题，供设计器“检查”按钮使用。"""

    try:
        issues = process_service.validate_process(process_id, db)
        return Result.success(ProcessValidationResponse.build(process_id, issues))
    except ProcessNotFoundError as exc:
        raise_process_http_error(exc)
