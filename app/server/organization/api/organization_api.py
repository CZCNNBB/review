"""人员、部门和租户成员管理接口。"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.common.schemas.result import Result
from app.server.organization.src.schemas.organization_schema import (
    DepartmentCreateRequest,
    DepartmentResponse,
    DepartmentUpdateRequest,
    PersonCreateRequest,
    PersonResponse,
    PersonUpdateRequest,
    TenantMemberCreateRequest,
    TenantMemberResponse,
    TenantMemberUpdateRequest,
)
from app.server.organization.src.service.exceptions import (
    OrganizationConflictError,
    OrganizationNotFoundError,
    OrganizationValidationError,
)
from app.server.organization.src.service.organization_service import OrganizationService
from app.server.tenant.api.dependencies import verify_admin_key


router = APIRouter()
organization_service = OrganizationService()


def raise_organization_http_error(exc: Exception) -> None:
    """将人员组织领域异常转换为明确的 HTTP 异常。"""

    if isinstance(exc, OrganizationNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, OrganizationConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, OrganizationValidationError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    raise exc


@router.post(
    "/admin/persons",
    response_model=Result[PersonResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_key)],
    summary="创建人员",
)
def create_person(
    request: PersonCreateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[PersonResponse]:
    """创建审批中心全局人员。"""

    try:
        person = organization_service.create_person(request, db)
        return Result.success(PersonResponse.model_validate(person))
    except OrganizationConflictError as exc:
        raise_organization_http_error(exc)


@router.get(
    "/admin/persons",
    response_model=Result[list[PersonResponse]],
    dependencies=[Depends(verify_admin_key)],
    summary="查询人员列表",
)
def list_persons(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_postgres_engine),
) -> Result[list[PersonResponse]]:
    """分页查询审批中心全局人员。"""

    persons = organization_service.list_persons(db, offset=offset, limit=limit)
    return Result.success([PersonResponse.model_validate(person) for person in persons])


@router.get(
    "/admin/persons/{person_id}",
    response_model=Result[PersonResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="查询人员详情",
)
def get_person(
    person_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[PersonResponse]:
    """查询指定全局人员。"""

    try:
        person = organization_service.get_person(person_id, db)
        return Result.success(PersonResponse.model_validate(person))
    except OrganizationNotFoundError as exc:
        raise_organization_http_error(exc)


@router.patch(
    "/admin/persons/{person_id}",
    response_model=Result[PersonResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="更新人员",
)
def update_person(
    person_id: UUID,
    request: PersonUpdateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[PersonResponse]:
    """更新人员资料或启停状态。"""

    try:
        person = organization_service.update_person(person_id, request, db)
        return Result.success(PersonResponse.model_validate(person))
    except (OrganizationNotFoundError, OrganizationConflictError) as exc:
        raise_organization_http_error(exc)


@router.post(
    "/admin/tenants/{tenant_id}/departments",
    response_model=Result[DepartmentResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_key)],
    summary="创建租户部门",
)
def create_department(
    tenant_id: UUID,
    request: DepartmentCreateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[DepartmentResponse]:
    """为租户创建平铺部门。"""

    try:
        department = organization_service.create_department(tenant_id, request, db)
        return Result.success(DepartmentResponse.model_validate(department))
    except (OrganizationNotFoundError, OrganizationConflictError) as exc:
        raise_organization_http_error(exc)


@router.get(
    "/admin/tenants/{tenant_id}/departments",
    response_model=Result[list[DepartmentResponse]],
    dependencies=[Depends(verify_admin_key)],
    summary="查询租户部门",
)
def list_departments(
    tenant_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[list[DepartmentResponse]]:
    """查询租户下的全部平铺部门。"""

    try:
        departments = organization_service.list_departments(tenant_id, db)
        return Result.success(
            [DepartmentResponse.model_validate(department) for department in departments]
        )
    except OrganizationNotFoundError as exc:
        raise_organization_http_error(exc)


@router.patch(
    "/admin/tenants/{tenant_id}/departments/{department_id}",
    response_model=Result[DepartmentResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="更新租户部门",
)
def update_department(
    tenant_id: UUID,
    department_id: UUID,
    request: DepartmentUpdateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[DepartmentResponse]:
    """更新租户部门名称或启停状态。"""

    try:
        department = organization_service.update_department(
            tenant_id,
            department_id,
            request,
            db,
        )
        return Result.success(DepartmentResponse.model_validate(department))
    except (OrganizationNotFoundError, OrganizationConflictError) as exc:
        raise_organization_http_error(exc)


@router.post(
    "/admin/tenants/{tenant_id}/members",
    response_model=Result[TenantMemberResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_key)],
    summary="创建租户成员",
)
def create_member(
    tenant_id: UUID,
    request: TenantMemberCreateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[TenantMemberResponse]:
    """将全局人员添加为租户成员。"""

    try:
        member = organization_service.create_member(tenant_id, request, db)
        response = organization_service.get_member_response(tenant_id, member.id, db)
        return Result.success(response)
    except (
        OrganizationNotFoundError,
        OrganizationConflictError,
        OrganizationValidationError,
    ) as exc:
        raise_organization_http_error(exc)


@router.get(
    "/admin/tenants/{tenant_id}/members",
    response_model=Result[list[TenantMemberResponse]],
    dependencies=[Depends(verify_admin_key)],
    summary="查询租户成员",
)
def list_members(
    tenant_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[list[TenantMemberResponse]]:
    """查询租户成员及人员、部门展示信息。"""

    try:
        return Result.success(organization_service.list_members(tenant_id, db))
    except OrganizationNotFoundError as exc:
        raise_organization_http_error(exc)


@router.get(
    "/admin/tenants/{tenant_id}/members/resolve",
    response_model=Result[TenantMemberResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="按外部用户标识解析租户成员",
)
def resolve_member(
    tenant_id: UUID,
    external_user_id: str = Query(min_length=1, max_length=128),
    db: Session = Depends(get_postgres_engine),
) -> Result[TenantMemberResponse]:
    """通过项目平台用户标识解析当前租户成员。"""

    try:
        response = organization_service.resolve_member_by_external_user_id(
            tenant_id,
            external_user_id,
            db,
        )
        return Result.success(response)
    except (OrganizationNotFoundError, OrganizationValidationError) as exc:
        raise_organization_http_error(exc)


@router.get(
    "/admin/tenants/{tenant_id}/members/{member_id}",
    response_model=Result[TenantMemberResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="查询租户成员详情",
)
def get_member(
    tenant_id: UUID,
    member_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[TenantMemberResponse]:
    """查询指定租户成员详情。"""

    try:
        return Result.success(
            organization_service.get_member_response(tenant_id, member_id, db)
        )
    except OrganizationNotFoundError as exc:
        raise_organization_http_error(exc)


@router.patch(
    "/admin/tenants/{tenant_id}/members/{member_id}",
    response_model=Result[TenantMemberResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="更新租户成员",
)
def update_member(
    tenant_id: UUID,
    member_id: UUID,
    request: TenantMemberUpdateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[TenantMemberResponse]:
    """更新成员部门、业务标识、展示名称或启停状态。"""

    try:
        response = organization_service.update_member(
            tenant_id,
            member_id,
            request,
            db,
        )
        return Result.success(response)
    except (
        OrganizationNotFoundError,
        OrganizationConflictError,
        OrganizationValidationError,
    ) as exc:
        raise_organization_http_error(exc)

