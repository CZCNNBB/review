"""全局人员、部门及其租户绑定管理接口。"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.common.schemas.result import Result
from app.common.scope import GlobalResourceScope
from app.common.security import verify_admin_key
from app.server.organization.src.schemas.organization_schema import (
    DepartmentCreateRequest,
    DepartmentMemberCreateRequest,
    DepartmentMemberResponse,
    DepartmentResponse,
    DepartmentUpdateRequest,
    PersonBindingRequest,
    PersonBindingResponse,
    PersonBindingUpdateRequest,
    PersonCreateRequest,
    PersonResponse,
    PersonUpdateRequest,
)
from app.server.organization.src.service.exceptions import (
    OrganizationConflictError,
    OrganizationNotFoundError,
    OrganizationValidationError,
)
from app.server.organization.src.service.organization_service import OrganizationService
from app.server.tenant.src.scope.tenant_scope import (
    RESOURCE_PERSON,
    TenantResourceAccessError,
    TenantResourceScope,
    create_resource_scope,
    is_tenancy_enabled,
)
from app.server.tenant.src.service.exceptions import TenantNotFoundError
from app.server.tenant.src.service.tenant_service import TenantService


router = APIRouter()
organization_service = OrganizationService()
tenant_service = TenantService()
global_scope = GlobalResourceScope()


def raise_organization_http_error(exc: Exception) -> None:
    """将人员组织及租户作用域异常转换为 HTTP 异常。"""

    if isinstance(exc, (OrganizationNotFoundError, TenantNotFoundError)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, (OrganizationConflictError, IntegrityError)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, (OrganizationValidationError, TenantResourceAccessError)):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    raise exc


def get_tenant_scope(
    tenant_id: UUID,
    resource_type: str,
    db: Session,
) -> TenantResourceScope:
    """校验租户并创建显式租户管理接口使用的资源作用域。"""

    if not is_tenancy_enabled():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前未启用租户能力，请使用全局管理接口",
        )

    tenant_service.get_tenant(tenant_id, db)
    scope = create_resource_scope(resource_type, tenant_id)
    if not isinstance(scope, TenantResourceScope):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="租户作用域初始化失败",
        )
    return scope


def commit_binding(db: Session, message: str) -> None:
    """提交租户绑定事务，并转换唯一约束冲突。"""

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise OrganizationConflictError(message) from exc


def build_person_binding_response(
    scope: TenantResourceScope,
    person_id: UUID,
    db: Session,
) -> PersonBindingResponse:
    """构造租户人员绑定及关联展示信息。"""

    binding = scope.get_binding(person_id, db)
    if not binding:
        raise OrganizationNotFoundError("租户人员绑定不存在")

    person = organization_service.get_person(person_id, db)
    return PersonBindingResponse(
        binding_id=binding.id,
        tenant_id=binding.tenant_id,
        person_id=person.id,
        person_name=person.name,
        employee_no=binding.employee_no,
        external_user_id=binding.external_user_id,
        display_name=binding.display_name,
        status=binding.status,
        created_at=binding.created_at,
        updated_at=binding.updated_at,
    )


@router.post(
    "/admin/persons",
    response_model=Result[PersonResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_key)],
    summary="创建全局人员",
)
def create_person(
    request: PersonCreateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[PersonResponse]:
    """创建与租户无关的全局人员。"""

    try:
        person = organization_service.create_person(request, db)
        return Result.success(PersonResponse.model_validate(person))
    except OrganizationConflictError as exc:
        raise_organization_http_error(exc)


@router.get(
    "/admin/persons",
    response_model=Result[list[PersonResponse]],
    dependencies=[Depends(verify_admin_key)],
    summary="查询全局人员",
)
def list_persons(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_postgres_engine),
) -> Result[list[PersonResponse]]:
    """不经过租户过滤分页查询全部人员。"""

    persons = organization_service.list_persons(
        db,
        scope=global_scope,
        offset=offset,
        limit=limit,
    )
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
    """查询全局人员详情。"""

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
    """更新全局人员资料或状态。"""

    try:
        person = organization_service.update_person(person_id, request, db)
        return Result.success(PersonResponse.model_validate(person))
    except (OrganizationNotFoundError, OrganizationConflictError) as exc:
        raise_organization_http_error(exc)


@router.post(
    "/admin/departments",
    response_model=Result[DepartmentResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_key)],
    summary="创建全局部门",
)
def create_department(
    request: DepartmentCreateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[DepartmentResponse]:
    """创建与租户无关的全局部门。"""

    try:
        department = organization_service.create_department(request, db)
        return Result.success(DepartmentResponse.model_validate(department))
    except OrganizationConflictError as exc:
        raise_organization_http_error(exc)


@router.get(
    "/admin/departments",
    response_model=Result[list[DepartmentResponse]],
    dependencies=[Depends(verify_admin_key)],
    summary="查询全局部门",
)
def list_departments(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_postgres_engine),
) -> Result[list[DepartmentResponse]]:
    """不经过租户过滤分页查询全部部门。"""

    departments = organization_service.list_departments(
        db,
        scope=global_scope,
        offset=offset,
        limit=limit,
    )
    return Result.success(
        [DepartmentResponse.model_validate(department) for department in departments]
    )


@router.get(
    "/admin/departments/{department_id}",
    response_model=Result[DepartmentResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="查询部门详情",
)
def get_department(
    department_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[DepartmentResponse]:
    """查询全局部门详情。"""

    try:
        department = organization_service.get_department(department_id, db)
        return Result.success(DepartmentResponse.model_validate(department))
    except OrganizationNotFoundError as exc:
        raise_organization_http_error(exc)


@router.patch(
    "/admin/departments/{department_id}",
    response_model=Result[DepartmentResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="更新部门",
)
def update_department(
    department_id: UUID,
    request: DepartmentUpdateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[DepartmentResponse]:
    """更新全局部门名称或状态。"""

    try:
        department = organization_service.update_department(department_id, request, db)
        return Result.success(DepartmentResponse.model_validate(department))
    except (OrganizationNotFoundError, OrganizationConflictError) as exc:
        raise_organization_http_error(exc)


@router.post(
    "/admin/departments/{department_id}/members",
    response_model=Result[DepartmentMemberResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_key)],
    summary="添加部门人员",
)
def add_department_member(
    department_id: UUID,
    request: DepartmentMemberCreateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[DepartmentMemberResponse]:
    """把全局人员加入全局部门。"""

    try:
        return Result.success(
            organization_service.add_department_member(
                department_id,
                request.person_id,
                db,
            )
        )
    except (
        OrganizationNotFoundError,
        OrganizationConflictError,
        OrganizationValidationError,
    ) as exc:
        raise_organization_http_error(exc)


@router.get(
    "/admin/departments/{department_id}/members",
    response_model=Result[list[DepartmentMemberResponse]],
    dependencies=[Depends(verify_admin_key)],
    summary="查询部门人员",
)
def list_department_members(
    department_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[list[DepartmentMemberResponse]]:
    """查询全局部门下的人员。"""

    try:
        return Result.success(
            organization_service.list_department_members(department_id, db)
        )
    except OrganizationNotFoundError as exc:
        raise_organization_http_error(exc)


@router.post(
    "/admin/departments/{department_id}/members/{person_id}/disable",
    response_model=Result[DepartmentMemberResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="停用部门人员关系",
)
def disable_department_member(
    department_id: UUID,
    person_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[DepartmentMemberResponse]:
    """停用指定人员部门关系。"""

    try:
        return Result.success(
            organization_service.disable_department_member(
                department_id,
                person_id,
                db,
            )
        )
    except OrganizationNotFoundError as exc:
        raise_organization_http_error(exc)


@router.post(
    "/admin/tenants/{tenant_id}/persons/bind",
    response_model=Result[PersonBindingResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_key)],
    summary="绑定租户人员",
)
def bind_person(
    tenant_id: UUID,
    request: PersonBindingRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[PersonBindingResponse]:
    """在人员模块 API 中建立租户人员绑定。"""

    try:
        organization_service.get_person(request.person_id, db)
        person_scope = get_tenant_scope(tenant_id, RESOURCE_PERSON, db)

        person_scope.bind(
            request.person_id,
            db,
            attributes=request.model_dump(exclude={"person_id"}),
        )
        commit_binding(db, "租户人员工号或外部用户标识已存在")
        return Result.success(
            build_person_binding_response(person_scope, request.person_id, db)
        )
    except (
        OrganizationNotFoundError,
        OrganizationConflictError,
        TenantNotFoundError,
        TenantResourceAccessError,
    ) as exc:
        raise_organization_http_error(exc)


@router.get(
    "/admin/tenants/{tenant_id}/persons",
    response_model=Result[list[PersonBindingResponse]],
    dependencies=[Depends(verify_admin_key)],
    summary="查询租户人员",
)
def list_tenant_persons(
    tenant_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[list[PersonBindingResponse]]:
    """通过 TenantScope 查询当前租户可见的人员。"""

    try:
        person_scope = get_tenant_scope(tenant_id, RESOURCE_PERSON, db)
        persons = organization_service.list_persons(
            db,
            scope=person_scope,
            offset=0,
            limit=500,
        )
        return Result.success(
            [
                build_person_binding_response(person_scope, person.id, db)
                for person in persons
            ]
        )
    except (OrganizationNotFoundError, TenantNotFoundError) as exc:
        raise_organization_http_error(exc)


@router.patch(
    "/admin/tenants/{tenant_id}/persons/{person_id}/binding",
    response_model=Result[PersonBindingResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="更新租户人员绑定",
)
def update_person_binding(
    tenant_id: UUID,
    person_id: UUID,
    request: PersonBindingUpdateRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[PersonBindingResponse]:
    """更新租户人员的租户内资料和状态。"""

    try:
        person_scope = get_tenant_scope(tenant_id, RESOURCE_PERSON, db)
        binding = person_scope.get_binding(person_id, db)
        if not binding:
            raise OrganizationNotFoundError("租户人员绑定不存在")

        update_data = request.model_dump(exclude_unset=True)
        for field_name, field_value in update_data.items():
            setattr(binding, field_name, field_value)
        db.add(binding)
        commit_binding(db, "租户人员工号或外部用户标识已存在")
        return Result.success(
            build_person_binding_response(person_scope, person_id, db)
        )
    except (
        OrganizationNotFoundError,
        OrganizationConflictError,
        TenantNotFoundError,
        TenantResourceAccessError,
    ) as exc:
        raise_organization_http_error(exc)
