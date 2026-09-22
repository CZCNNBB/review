"""租户流程授权、业务动作授权和审批使用记录管理接口。"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.common.schemas.result import Result
from app.common.security import verify_admin_key
from app.server.integration.src.service.exceptions import (
    BusinessActionNotFoundError,
)
from app.server.process.api.process_api import raise_process_http_error
from app.server.process.src.service.exceptions import ProcessNotFoundError
from app.server.process.src.utils.duration import elapsed_ms
from app.server.tenant.src.schemas.tenant_binding_schema import (
    BindingStatusUpdateRequest,
    BusinessActionBindingCreateRequest,
    BusinessActionBindingResponse,
    ProcessBindingCreateRequest,
    ProcessBindingResponse,
    ProcessUsageRecordResponse,
)
from app.server.tenant.src.service.tenant_binding_service import (
    TenantBindingService,
    UsageRecordView,
)
from app.server.tenant.src.service.exceptions import (
    TenantBindingConflictError,
    TenantBindingNotFoundError,
    TenantNotFoundError,
)


router = APIRouter()
tenant_binding_service = TenantBindingService()


def raise_tenant_binding_http_error(exc: Exception) -> None:
    """把租户授权管理相关的领域异常转换成明确的 HTTP 异常。"""

    if isinstance(exc, ProcessNotFoundError):
        raise_process_http_error(exc)
    if isinstance(
        exc,
        (BusinessActionNotFoundError, TenantBindingNotFoundError, TenantNotFoundError),
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    if isinstance(exc, TenantBindingConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    raise exc


def build_usage_record_response(view: UsageRecordView) -> ProcessUsageRecordResponse:
    """把使用记录和从 process 运行表读取的摘要组装成响应。"""

    record = view.record
    overview = view.overview
    started_at = overview.started_at if overview else None
    finished_at = overview.finished_at if overview else None

    return ProcessUsageRecordResponse(
        id=record.id,
        tenant_id=record.tenant_id,
        process_id=record.process_id,
        process_version_id=record.process_version_id,
        approval_instance_id=record.approval_instance_id,
        business_key=record.business_key,
        action_code=record.action_code,
        created_at=record.created_at,
        approval_status=overview.status if overview else None,
        approval_title=overview.title if overview else None,
        current_node_name=overview.current_node_name if overview else None,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=elapsed_ms(started_at, finished_at),
    )


# ---------------------------------------------------------------------------
# 租户审批流授权
# ---------------------------------------------------------------------------


@router.post(
    "/admin/tenants/{tenant_id}/process-bindings",
    response_model=Result[ProcessBindingResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_key)],
    summary="授权租户使用审批流",
)
def create_process_binding(
    tenant_id: UUID,
    request: ProcessBindingCreateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[ProcessBindingResponse]:
    """授予租户审批流使用权，授权前确认流程存在。"""

    try:
        binding = tenant_binding_service.create_process_binding(
            tenant_id,
            request.process_id,
            db,
        )
        return Result.success(ProcessBindingResponse.model_validate(binding))
    except (
        ProcessNotFoundError,
        BusinessActionNotFoundError,
        TenantNotFoundError,
        TenantBindingConflictError,
    ) as exc:
        raise_tenant_binding_http_error(exc)


@router.get(
    "/admin/tenants/{tenant_id}/process-bindings",
    response_model=Result[list[ProcessBindingResponse]],
    dependencies=[Depends(verify_admin_key)],
    summary="查询租户审批流授权",
)
def list_process_bindings(
    tenant_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[list[ProcessBindingResponse]]:
    """查询租户的全部审批流授权，包含已经停用的记录。"""

    bindings = tenant_binding_service.list_process_bindings(tenant_id, db)
    return Result.success(
        [ProcessBindingResponse.model_validate(binding) for binding in bindings]
    )


@router.patch(
    "/admin/tenants/{tenant_id}/process-bindings/{binding_id}",
    response_model=Result[ProcessBindingResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="启用或停用租户审批流授权",
)
def update_process_binding(
    tenant_id: UUID,
    binding_id: UUID,
    request: BindingStatusUpdateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[ProcessBindingResponse]:
    """切换审批流授权状态，停用后不影响已经运行的审批实例。"""

    try:
        binding = tenant_binding_service.update_process_binding_status(
            tenant_id,
            binding_id,
            request.status,
            db,
        )
        return Result.success(ProcessBindingResponse.model_validate(binding))
    except TenantBindingNotFoundError as exc:
        raise_tenant_binding_http_error(exc)


# ---------------------------------------------------------------------------
# 租户业务动作授权
# ---------------------------------------------------------------------------


@router.post(
    "/admin/tenants/{tenant_id}/business-action-bindings",
    response_model=Result[BusinessActionBindingResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_key)],
    summary="授权租户使用业务动作",
)
def create_business_action_binding(
    tenant_id: UUID,
    request: BusinessActionBindingCreateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[BusinessActionBindingResponse]:
    """授予租户业务动作使用权，授权前确认动作存在。"""

    try:
        binding = tenant_binding_service.create_business_action_binding(
            tenant_id,
            request.business_action_id,
            db,
        )
        return Result.success(BusinessActionBindingResponse.model_validate(binding))
    except (
        BusinessActionNotFoundError,
        TenantNotFoundError,
        TenantBindingConflictError,
    ) as exc:
        raise_tenant_binding_http_error(exc)


@router.get(
    "/admin/tenants/{tenant_id}/business-action-bindings",
    response_model=Result[list[BusinessActionBindingResponse]],
    dependencies=[Depends(verify_admin_key)],
    summary="查询租户业务动作授权",
)
def list_business_action_bindings(
    tenant_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[list[BusinessActionBindingResponse]]:
    """查询租户的全部业务动作授权，包含已经停用的记录。"""

    bindings = tenant_binding_service.list_business_action_bindings(tenant_id, db)
    return Result.success(
        [
            BusinessActionBindingResponse.model_validate(binding)
            for binding in bindings
        ]
    )


@router.patch(
    "/admin/tenants/{tenant_id}/business-action-bindings/{binding_id}",
    response_model=Result[BusinessActionBindingResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="启用或停用租户业务动作授权",
)
def update_business_action_binding(
    tenant_id: UUID,
    binding_id: UUID,
    request: BindingStatusUpdateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[BusinessActionBindingResponse]:
    """切换业务动作授权状态，停用后该租户不能在新申请中使用这个动作。"""

    try:
        binding = tenant_binding_service.update_business_action_binding_status(
            tenant_id,
            binding_id,
            request.status,
            db,
        )
        return Result.success(BusinessActionBindingResponse.model_validate(binding))
    except TenantBindingNotFoundError as exc:
        raise_tenant_binding_http_error(exc)


# ---------------------------------------------------------------------------
# 租户审批使用记录
# ---------------------------------------------------------------------------


@router.get(
    "/admin/tenants/{tenant_id}/process-usage-records",
    response_model=Result[list[ProcessUsageRecordResponse]],
    dependencies=[Depends(verify_admin_key)],
    summary="查询租户审批使用记录",
)
def list_process_usage_records(
    tenant_id: UUID,
    process_id: UUID | None = Query(default=None),
    business_key: str | None = Query(default=None, max_length=200),
    action_code: str | None = Query(default=None, max_length=100),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_postgres_engine),
) -> Result[list[ProcessUsageRecordResponse]]:
    """按租户查询审批使用记录，运行状态从 process 运行表读取后组装。"""

    views = tenant_binding_service.list_usage_records(
        tenant_id,
        db,
        process_id=process_id,
        business_key=business_key,
        action_code=action_code,
        created_from=created_from,
        created_to=created_to,
        offset=offset,
        limit=limit,
    )
    return Result.success(
        [build_usage_record_response(view) for view in views]
    )


@router.get(
    "/admin/tenants/{tenant_id}/process-usage-records/{record_id}",
    response_model=Result[ProcessUsageRecordResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="查询租户审批使用记录详情",
)
def get_process_usage_record(
    tenant_id: UUID,
    record_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[ProcessUsageRecordResponse]:
    """查询单条使用记录及其对应的审批实例状态。"""

    try:
        view = tenant_binding_service.get_usage_record(tenant_id, record_id, db)
        return Result.success(build_usage_record_response(view))
    except TenantBindingNotFoundError as exc:
        raise_tenant_binding_http_error(exc)
