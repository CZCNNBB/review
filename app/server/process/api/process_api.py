"""审批流主体、版本、编排和发布管理接口。"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.common.schemas.result import Result
from app.common.security import verify_admin_key
from app.server.process.src.models.process_model import ApprovalProcessVersion
from app.server.process.src.schemas.process_schema import (
    ProcessCreateRequest,
    ProcessGraphNodeResponse,
    ProcessGraphResponse,
    ProcessGraphSaveRequest,
    ProcessResponse,
    ProcessValidationIssueResponse,
    ProcessValidationResponse,
    ProcessVersionResponse,
)
from app.server.process.src.service.exceptions import (
    ProcessConflictError,
    ProcessNotFoundError,
    ProcessStateError,
    ProcessValidationError,
)
from app.server.process.src.service.process_service import (
    ProcessGraphView,
    ProcessOverview,
    ProcessService,
)


router = APIRouter()
process_service = ProcessService()


def raise_process_http_error(exc: Exception) -> None:
    """将审批流领域异常转换为明确的 HTTP 异常。"""

    if isinstance(exc, ProcessNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, (ProcessConflictError, ProcessStateError)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, ProcessValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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


def build_process_response(overview: ProcessOverview) -> ProcessResponse:
    """把流程及其版本摘要转换为接口响应。"""

    process = overview.process
    current_version = overview.current_version
    draft_version = overview.draft_version
    return ProcessResponse(
        id=process.id,
        name=process.name,
        description=process.description,
        status=process.status,
        current_version_id=current_version.id if current_version else None,
        current_version_no=current_version.version_no if current_version else None,
        draft_version_id=draft_version.id if draft_version else None,
        draft_version_no=draft_version.version_no if draft_version else None,
        node_count=overview.node_count,
        created_at=process.created_at,
        updated_at=process.updated_at,
    )


def build_version_response(
    version: ApprovalProcessVersion,
    node_count: int,
) -> ProcessVersionResponse:
    """把流程版本模型转换为概要响应。"""

    return ProcessVersionResponse(
        id=version.id,
        process_id=version.process_id,
        version_no=version.version_no,
        status=version.status,
        name=version.name,
        description=version.description,
        revision=version.revision,
        node_count=node_count,
        created_at=version.created_at,
        updated_at=version.updated_at,
        published_at=version.published_at,
    )


def build_graph_response(graph_view: ProcessGraphView) -> ProcessGraphResponse:
    """把确定版本的整图数据转换成接口响应。"""

    version = graph_view.version
    nodes: list[ProcessGraphNodeResponse] = []
    for node in graph_view.nodes:
        definition = graph_view.definitions.get(node.node_definition_id)
        nodes.append(
            ProcessGraphNodeResponse(
                id=node.id,
                node_definition_id=node.node_definition_id,
                node_type=node.node_type,
                node_definition_name=definition.name if definition else None,
                name=node.name,
                config=node.config_json,
                position=node.position_json,
                created_at=node.created_at,
                updated_at=node.updated_at,
            )
        )

    return ProcessGraphResponse(
        process_id=version.process_id,
        version_id=version.id,
        version_no=version.version_no,
        version_status=version.status,
        revision=version.revision,
        name=version.name,
        description=version.description,
        form_schema=version.form_schema_json,
        form_ui_schema=version.form_ui_schema_json,
        orchestration=version.orchestration_json,
        nodes=nodes,
        created_at=version.created_at,
        updated_at=version.updated_at,
        published_at=version.published_at,
    )


@router.post(
    "/admin/processes",
    response_model=Result[ProcessResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_key)],
    summary="创建审批流和 V1 草稿",
)
def create_process(
    request: ProcessCreateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[ProcessResponse]:
    """创建稳定流程身份，并同时建立可编辑的 V1 草稿。"""

    overview = process_service.create_process(request, db)
    return Result.success(build_process_response(overview))


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
    """分页查询审批流及当前版本和草稿摘要。"""

    overviews = process_service.list_processes(db, offset=offset, limit=limit)
    return Result.success([build_process_response(item) for item in overviews])


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
    """查询审批流稳定身份和版本摘要。"""

    try:
        return Result.success(
            build_process_response(process_service.get_overview(process_id, db))
        )
    except ProcessNotFoundError as exc:
        raise_process_http_error(exc)


@router.get(
    "/admin/processes/{process_id}/versions",
    response_model=Result[list[ProcessVersionResponse]],
    dependencies=[Depends(verify_admin_key)],
    summary="查询流程版本列表",
)
def list_process_versions(
    process_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[list[ProcessVersionResponse]]:
    """按版本号倒序返回指定流程的全部版本。"""

    try:
        versions = process_service.list_versions(process_id, db)
        return Result.success(
            [
                build_version_response(version, node_count)
                for version, node_count in versions
            ]
        )
    except ProcessNotFoundError as exc:
        raise_process_http_error(exc)


@router.post(
    "/admin/processes/{process_id}/draft",
    response_model=Result[ProcessVersionResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_key)],
    summary="创建下一版草稿",
)
def create_process_draft(
    process_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[ProcessVersionResponse]:
    """从当前发布版本复制下一版草稿；已有草稿时直接返回。"""

    try:
        version = process_service.create_draft(process_id, db)
        node_count = len(process_service.get_graph(version.id, db).nodes)
        return Result.success(build_version_response(version, node_count))
    except (ProcessNotFoundError, ProcessStateError, ProcessConflictError) as exc:
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
    """复制当前可见版本，创建一条拥有 V1 草稿的新流程。"""

    try:
        return Result.success(
            build_process_response(process_service.copy_process(process_id, db))
        )
    except (
        ProcessNotFoundError,
        ProcessStateError,
        ProcessConflictError,
    ) as exc:
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
    """停用已经发布过的流程。"""

    try:
        return Result.success(
            build_process_response(process_service.disable_process(process_id, db))
        )
    except (ProcessNotFoundError, ProcessStateError) as exc:
        raise_process_http_error(exc)


@router.get(
    "/admin/process-versions/{version_id}/graph",
    response_model=Result[ProcessGraphResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="读取版本编排",
)
def get_process_version_graph(
    version_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[ProcessGraphResponse]:
    """读取草稿或历史发布版本的完整画布。"""

    try:
        return Result.success(
            build_graph_response(process_service.get_graph(version_id, db))
        )
    except ProcessNotFoundError as exc:
        raise_process_http_error(exc)


@router.put(
    "/admin/process-versions/{version_id}/graph",
    response_model=Result[ProcessGraphResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="保存草稿版本编排",
)
def save_process_version_graph(
    version_id: UUID,
    request: ProcessGraphSaveRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[ProcessGraphResponse]:
    """按 revision 保存草稿整图，已发布版本拒绝修改。"""

    try:
        graph_view = process_service.save_graph(version_id, request, db)
        return Result.success(build_graph_response(graph_view))
    except (
        ProcessNotFoundError,
        ProcessConflictError,
        ProcessStateError,
        ProcessValidationError,
    ) as exc:
        raise_process_http_error(exc)


@router.post(
    "/admin/process-versions/{version_id}/validate",
    response_model=Result[ProcessValidationResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="校验流程版本完整性",
)
def validate_process_version(
    version_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[ProcessValidationResponse]:
    """校验指定版本并返回全部结构化问题。"""

    try:
        version = process_service.get_version(version_id, db)
        issues = process_service.validate_version(version_id, db)
        return Result.success(
            ProcessValidationResponse.build(version.process_id, version.id, issues)
        )
    except ProcessNotFoundError as exc:
        raise_process_http_error(exc)


@router.post(
    "/admin/process-versions/{version_id}/publish",
    response_model=Result[ProcessResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="发布流程版本",
)
def publish_process_version(
    version_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[ProcessResponse]:
    """发布草稿并把它原子切换为流程当前版本。"""

    try:
        overview = process_service.publish_version(version_id, db)
        return Result.success(build_process_response(overview))
    except (
        ProcessNotFoundError,
        ProcessStateError,
        ProcessConflictError,
        ProcessValidationError,
    ) as exc:
        raise_process_http_error(exc)
