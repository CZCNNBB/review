"""租户、API Key 与回调凭据管理接口。"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.common.schemas.result import Result
from app.server.tenant.api.dependencies import TenantAuthContext, get_tenant_context, verify_admin_key
from app.server.tenant.src.schemas.tenant_schema import (
    ApiKeyCreateRequest,
    ApiKeyCreatedResponse,
    ApiKeyResponse,
    CallbackCredentialCreateRequest,
    CallbackCredentialResponse,
    TenantContextResponse,
    TenantCreateRequest,
    TenantResponse,
    TenantUpdateRequest,
)
from app.server.tenant.src.service.exceptions import (
    CredentialConfigurationError,
    CredentialNotFoundError,
    TenantConflictError,
    TenantNotFoundError,
)
from app.server.tenant.src.service.tenant_service import TenantService


router = APIRouter()
tenant_service = TenantService()


def raise_tenant_http_error(exc: Exception) -> None:
    """将租户领域异常转换为明确的 HTTP 异常。"""

    if isinstance(exc, (TenantNotFoundError, CredentialNotFoundError)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, TenantConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, CredentialConfigurationError):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    raise exc


@router.post(
    "/admin/tenants",
    response_model=Result[TenantResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_key)],
    summary="创建租户",
)
def create_tenant(
    request: TenantCreateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[TenantResponse]:
    """创建接入审批中心的业务系统租户。"""

    try:
        tenant = tenant_service.create_tenant(request, db)
        return Result.success(TenantResponse.model_validate(tenant))
    except (TenantConflictError, TenantNotFoundError) as exc:
        raise_tenant_http_error(exc)


@router.get(
    "/admin/tenants",
    response_model=Result[list[TenantResponse]],
    dependencies=[Depends(verify_admin_key)],
    summary="查询租户列表",
)
def list_tenants(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_postgres_engine),
) -> Result[list[TenantResponse]]:
    """分页查询全部租户。"""

    tenants = tenant_service.list_tenants(db, offset=offset, limit=limit)
    return Result.success([TenantResponse.model_validate(tenant) for tenant in tenants])


@router.get(
    "/admin/tenants/{tenant_id}",
    response_model=Result[TenantResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="查询租户详情",
)
def get_tenant(
    tenant_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[TenantResponse]:
    """按主键查询租户详情。"""

    try:
        tenant = tenant_service.get_tenant(tenant_id, db)
        return Result.success(TenantResponse.model_validate(tenant))
    except TenantNotFoundError as exc:
        raise_tenant_http_error(exc)


@router.patch(
    "/admin/tenants/{tenant_id}",
    response_model=Result[TenantResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="更新租户",
)
def update_tenant(
    tenant_id: UUID,
    request: TenantUpdateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[TenantResponse]:
    """更新租户名称、描述、默认回调地址或状态。"""

    try:
        tenant = tenant_service.update_tenant(tenant_id, request, db)
        return Result.success(TenantResponse.model_validate(tenant))
    except TenantNotFoundError as exc:
        raise_tenant_http_error(exc)


@router.post(
    "/admin/tenants/{tenant_id}/api-keys",
    response_model=Result[ApiKeyCreatedResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_key)],
    summary="创建租户 API Key",
)
def create_api_key(
    tenant_id: UUID,
    request: ApiKeyCreateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[ApiKeyCreatedResponse]:
    """创建 API Key，并在响应中返回可供业务系统使用的完整明文。"""

    try:
        api_key = tenant_service.create_api_key(
            tenant_id=tenant_id,
            name=request.name,
            expires_at=request.expires_at,
            db=db,
        )
        response = ApiKeyCreatedResponse.model_validate(api_key)
        return Result.success(response)
    except (TenantNotFoundError, TenantConflictError) as exc:
        raise_tenant_http_error(exc)


@router.get(
    "/admin/tenants/{tenant_id}/api-keys",
    response_model=Result[list[ApiKeyResponse]],
    dependencies=[Depends(verify_admin_key)],
    summary="查询租户 API Key",
)
def list_api_keys(
    tenant_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[list[ApiKeyResponse]]:
    """查询 API Key 列表，供管理页面查看和复制明文。"""

    try:
        api_keys = tenant_service.list_api_keys(tenant_id, db)
        return Result.success([ApiKeyResponse.model_validate(item) for item in api_keys])
    except TenantNotFoundError as exc:
        raise_tenant_http_error(exc)


@router.post(
    "/admin/tenants/{tenant_id}/api-keys/{api_key_id}/revoke",
    response_model=Result[ApiKeyResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="撤销租户 API Key",
)
def revoke_api_key(
    tenant_id: UUID,
    api_key_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[ApiKeyResponse]:
    """撤销指定 API Key，重复调用返回当前撤销状态。"""

    try:
        api_key = tenant_service.revoke_api_key(tenant_id, api_key_id, db)
        return Result.success(ApiKeyResponse.model_validate(api_key))
    except CredentialNotFoundError as exc:
        raise_tenant_http_error(exc)


@router.post(
    "/admin/tenants/{tenant_id}/callback-credentials",
    response_model=Result[CallbackCredentialResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_key)],
    summary="配置回调 Service Token",
)
def create_callback_credential(
    tenant_id: UUID,
    request: CallbackCredentialCreateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[CallbackCredentialResponse]:
    """保存业务系统为审批中心服务账号签发的 Service Token。

    Token 由业务系统签发，审批中心加密保存后只返回凭据元数据，不回显 Token 明文。
    租户原有的有效凭据会在同一个事务中撤销。
    """

    try:
        credential = tenant_service.create_callback_credential(
            tenant_id=tenant_id,
            name=request.name,
            token=request.token,
            header_name=request.header_name,
            token_prefix=request.token_prefix,
            expires_at=request.expires_at,
            db=db,
        )
        return Result.success(CallbackCredentialResponse.model_validate(credential))
    except (
        TenantNotFoundError,
        TenantConflictError,
        CredentialConfigurationError,
    ) as exc:
        raise_tenant_http_error(exc)


@router.get(
    "/admin/tenants/{tenant_id}/callback-credentials",
    response_model=Result[list[CallbackCredentialResponse]],
    dependencies=[Depends(verify_admin_key)],
    summary="查询回调 Service Token 凭据",
)
def list_callback_credentials(
    tenant_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[list[CallbackCredentialResponse]]:
    """查询回调凭据元数据，不返回 Token 明文和密文。"""

    try:
        credentials = tenant_service.list_callback_credentials(tenant_id, db)
        return Result.success(
            [CallbackCredentialResponse.model_validate(item) for item in credentials]
        )
    except TenantNotFoundError as exc:
        raise_tenant_http_error(exc)


@router.post(
    "/admin/tenants/{tenant_id}/callback-credentials/{credential_id}/revoke",
    response_model=Result[CallbackCredentialResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="撤销回调 Service Token 凭据",
)
def revoke_callback_credential(
    tenant_id: UUID,
    credential_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[CallbackCredentialResponse]:
    """撤销指定回调 Service Token 凭据，撤销后不能恢复。"""

    try:
        credential = tenant_service.revoke_callback_credential(tenant_id, credential_id, db)
        return Result.success(CallbackCredentialResponse.model_validate(credential))
    except CredentialNotFoundError as exc:
        raise_tenant_http_error(exc)


@router.get(
    "/tenant/context",
    response_model=Result[TenantContextResponse],
    summary="验证 API Key 并查询当前租户",
)
def get_current_tenant(
    context: TenantAuthContext = Depends(get_tenant_context),
) -> Result[TenantContextResponse]:
    """返回经过 API Key 验证的可信租户上下文。"""

    return Result.success(TenantContextResponse(**context.__dict__))
