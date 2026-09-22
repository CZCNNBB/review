"""业务动作管理接口和业务接入错误码映射。"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.common.schemas.result import Result
from app.common.security import verify_admin_key
from app.server.integration.src.constants import ACTION_STATUS_PATTERN
from app.server.integration.src.schemas.business_action_schema import (
    BusinessActionCreateRequest,
    BusinessActionResponse,
    BusinessActionUpdateRequest,
)
from app.server.integration.src.service.business_action_service import (
    BusinessActionService,
)
from app.server.integration.src.service.exceptions import (
    BusinessActionConflictError,
    BusinessActionNotFoundError,
    BusinessActionStateError,
    BusinessActionValidationError,
)
from app.server.process.src.schemas.process_schema import (
    ProcessValidationIssueResponse,
)
from app.server.tenant.src.scope.tenant_scope import TenantResourceAccessError


router = APIRouter()
business_action_service = BusinessActionService()


def raise_business_access_http_error(exc: Exception) -> None:
    """把业务接入领域的异常转换成统一错误码的 HTTP 异常。

    发起审批接口和业务动作管理接口共用本函数，保证同一类失败在两条链路上返回相同的
    状态码。无权访问时不区分具体原因，避免向调用方暴露其他租户是否绑定了某个资源。
    """

    if isinstance(exc, TenantResourceAccessError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    if isinstance(exc, BusinessActionNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    if isinstance(exc, (BusinessActionConflictError, BusinessActionStateError)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if isinstance(exc, BusinessActionValidationError):
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


@router.post(
    "/admin/business-actions",
    response_model=Result[BusinessActionResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_key)],
    summary="创建业务动作",
)
def create_business_action(
    request: BusinessActionCreateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[BusinessActionResponse]:
    """创建审批通过后可以执行的业务动作及其参数规则。"""

    try:
        action = business_action_service.create_action(request, db)
        return Result.success(BusinessActionResponse.from_action(action))
    except (
        BusinessActionConflictError,
        BusinessActionValidationError,
    ) as exc:
        raise_business_access_http_error(exc)


@router.get(
    "/admin/business-actions",
    response_model=Result[list[BusinessActionResponse]],
    dependencies=[Depends(verify_admin_key)],
    summary="查询业务动作列表",
)
def list_business_actions(
    action_status: str | None = Query(
        default=None,
        alias="status",
        pattern=ACTION_STATUS_PATTERN,
    ),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_postgres_engine),
) -> Result[list[BusinessActionResponse]]:
    """分页查询业务动作，可按状态筛选。"""

    actions = business_action_service.list_actions(
        db,
        status=action_status,
        offset=offset,
        limit=limit,
    )
    return Result.success(
        [BusinessActionResponse.from_action(action) for action in actions]
    )


@router.get(
    "/admin/business-actions/{action_id}",
    response_model=Result[BusinessActionResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="查询业务动作详情",
)
def get_business_action(
    action_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[BusinessActionResponse]:
    """按主键查询业务动作配置。"""

    try:
        action = business_action_service.get_action(action_id, db)
        return Result.success(BusinessActionResponse.from_action(action))
    except BusinessActionNotFoundError as exc:
        raise_business_access_http_error(exc)


@router.patch(
    "/admin/business-actions/{action_id}",
    response_model=Result[BusinessActionResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="更新业务动作",
)
def update_business_action(
    action_id: UUID,
    request: BusinessActionUpdateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[BusinessActionResponse]:
    """更新业务动作的展示信息、调用配置或状态。

    停用后的业务动作不能用于新申请，已经发起审批的实例仍按审批记录继续处理。
    """

    try:
        action = business_action_service.update_action(action_id, request, db)
        return Result.success(BusinessActionResponse.from_action(action))
    except (
        BusinessActionNotFoundError,
        BusinessActionValidationError,
    ) as exc:
        raise_business_access_http_error(exc)
