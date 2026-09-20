"""人员、部门和租户成员业务逻辑。"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.server.organization.src.models.organization_model import (
    Department,
    Person,
    TenantMember,
)
from app.server.organization.src.repository.organization_repository import OrganizationRepository
from app.server.organization.src.schemas.organization_schema import (
    DepartmentCreateRequest,
    DepartmentUpdateRequest,
    PersonCreateRequest,
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
from app.server.tenant.src.repository.tenant_repository import TenantRepository


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""

    return datetime.now(timezone.utc)


class OrganizationService:
    """提供全局人员、租户部门和租户成员管理能力。"""

    def __init__(
        self,
        repository: OrganizationRepository | None = None,
        tenant_repository: TenantRepository | None = None,
    ):
        """初始化服务并允许测试注入数据访问对象。"""

        self.repository = repository or OrganizationRepository()
        self.tenant_repository = tenant_repository or TenantRepository()

    def create_person(self, request: PersonCreateRequest, db: Session) -> Person:
        """创建全局人员。"""

        person = Person(
            name=request.name,
            mobile=request.mobile,
            email=request.email,
        )
        self.repository.add(person, db)
        self._commit_or_conflict(db, "人员信息冲突")
        db.refresh(person)
        return person

    def list_persons(self, db: Session, offset: int = 0, limit: int = 100) -> list[Person]:
        """分页查询全局人员。"""

        return self.repository.list_persons(db, offset=offset, limit=limit)

    def get_person(self, person_id: UUID, db: Session) -> Person:
        """查询全局人员，不存在时抛出领域异常。"""

        person = self.repository.get_person(person_id, db)
        if not person:
            raise OrganizationNotFoundError("人员不存在")
        return person

    def update_person(
        self,
        person_id: UUID,
        request: PersonUpdateRequest,
        db: Session,
    ) -> Person:
        """更新人员资料或启停状态。"""

        person = self.get_person(person_id, db)
        update_data = request.model_dump(exclude_unset=True)
        for field_name, field_value in update_data.items():
            setattr(person, field_name, field_value)

        person.updated_at = utc_now()
        self.repository.add(person, db)
        self._commit_or_conflict(db, "人员信息冲突")
        db.refresh(person)
        return person

    def create_department(
        self,
        tenant_id: UUID,
        request: DepartmentCreateRequest,
        db: Session,
    ) -> Department:
        """为租户创建平铺部门。"""

        self._ensure_tenant_exists(tenant_id, db)
        existing_department = self.repository.get_department_by_code(
            tenant_id,
            request.code,
            db,
        )
        if existing_department:
            raise OrganizationConflictError(f"部门编码 {request.code} 已存在")

        department = Department(
            tenant_id=tenant_id,
            code=request.code,
            name=request.name,
        )
        self.repository.add(department, db)
        self._commit_or_conflict(db, "租户内部门编码已存在")
        db.refresh(department)
        return department

    def list_departments(self, tenant_id: UUID, db: Session) -> list[Department]:
        """查询租户下的全部部门。"""

        self._ensure_tenant_exists(tenant_id, db)
        return self.repository.list_departments(tenant_id, db)

    def get_department(self, tenant_id: UUID, department_id: UUID, db: Session) -> Department:
        """查询属于指定租户的部门。"""

        department = self.repository.get_department(department_id, db)
        if not department or department.tenant_id != tenant_id:
            raise OrganizationNotFoundError("部门不存在")
        return department

    def update_department(
        self,
        tenant_id: UUID,
        department_id: UUID,
        request: DepartmentUpdateRequest,
        db: Session,
    ) -> Department:
        """更新租户部门名称或启停状态。"""

        department = self.get_department(tenant_id, department_id, db)
        update_data = request.model_dump(exclude_unset=True)
        for field_name, field_value in update_data.items():
            setattr(department, field_name, field_value)

        department.updated_at = utc_now()
        self.repository.add(department, db)
        self._commit_or_conflict(db, "部门信息冲突")
        db.refresh(department)
        return department

    def create_member(
        self,
        tenant_id: UUID,
        request: TenantMemberCreateRequest,
        db: Session,
    ) -> TenantMember:
        """将全局人员添加为指定租户的成员。"""

        self._ensure_tenant_exists(tenant_id, db)
        person = self.get_person(request.person_id, db)
        if person.status != "ENABLED":
            raise OrganizationValidationError("已停用人员不能加入租户")

        if self.repository.get_member_by_person(tenant_id, request.person_id, db):
            raise OrganizationConflictError("该人员已经是当前租户成员")

        if request.department_id:
            self._ensure_enabled_department(tenant_id, request.department_id, db)

        member = TenantMember(
            tenant_id=tenant_id,
            person_id=request.person_id,
            department_id=request.department_id,
            employee_no=request.employee_no,
            external_user_id=request.external_user_id,
            display_name=request.display_name,
        )
        self.repository.add(member, db)
        self._commit_or_conflict(db, "租户成员编号或外部用户标识已存在")
        db.refresh(member)
        return member

    def list_members(self, tenant_id: UUID, db: Session) -> list[TenantMemberResponse]:
        """查询租户成员并补充人员与部门展示信息。"""

        self._ensure_tenant_exists(tenant_id, db)
        members = self.repository.list_members(tenant_id, db)
        return [self._build_member_response(member, db) for member in members]

    def get_member(
        self,
        tenant_id: UUID,
        member_id: UUID,
        db: Session,
    ) -> TenantMember:
        """查询属于指定租户的成员。"""

        member = self.repository.get_member(member_id, db)
        if not member or member.tenant_id != tenant_id:
            raise OrganizationNotFoundError("租户成员不存在")
        return member

    def get_member_response(
        self,
        tenant_id: UUID,
        member_id: UUID,
        db: Session,
    ) -> TenantMemberResponse:
        """查询租户成员详情并补充展示字段。"""

        member = self.get_member(tenant_id, member_id, db)
        return self._build_member_response(member, db)

    def resolve_member_by_external_user_id(
        self,
        tenant_id: UUID,
        external_user_id: str,
        db: Session,
    ) -> TenantMemberResponse:
        """通过项目平台用户标识解析租户成员。"""

        self._ensure_tenant_exists(tenant_id, db)
        normalized_external_user_id = external_user_id.strip()
        if not normalized_external_user_id:
            raise OrganizationValidationError("外部用户标识不能为空")

        member = self.repository.get_member_by_external_user_id(
            tenant_id,
            normalized_external_user_id,
            db,
        )
        if not member:
            raise OrganizationNotFoundError("未找到对应的租户成员")
        return self._build_member_response(member, db)

    def update_member(
        self,
        tenant_id: UUID,
        member_id: UUID,
        request: TenantMemberUpdateRequest,
        db: Session,
    ) -> TenantMemberResponse:
        """更新租户成员资料、部门或启停状态。"""

        member = self.get_member(tenant_id, member_id, db)
        update_data = request.model_dump(exclude_unset=True)

        if "department_id" in update_data and update_data["department_id"] is not None:
            self._ensure_enabled_department(tenant_id, update_data["department_id"], db)

        for field_name, field_value in update_data.items():
            setattr(member, field_name, field_value)

        member.updated_at = utc_now()
        self.repository.add(member, db)
        self._commit_or_conflict(db, "租户成员编号或外部用户标识已存在")
        db.refresh(member)
        return self._build_member_response(member, db)

    def _ensure_tenant_exists(self, tenant_id: UUID, db: Session) -> None:
        """确认租户存在。"""

        if not self.tenant_repository.get_tenant_by_id(tenant_id, db):
            raise OrganizationNotFoundError("租户不存在")

    def _ensure_enabled_department(
        self,
        tenant_id: UUID,
        department_id: UUID,
        db: Session,
    ) -> Department:
        """确认部门属于当前租户且处于启用状态。"""

        department = self.get_department(tenant_id, department_id, db)
        if department.status != "ENABLED":
            raise OrganizationValidationError("已停用部门不能绑定新成员")
        return department

    def _build_member_response(
        self,
        member: TenantMember,
        db: Session,
    ) -> TenantMemberResponse:
        """将成员模型转换为包含人员和部门名称的响应。"""

        person = self.repository.get_person(member.person_id, db)
        if not person:
            raise OrganizationNotFoundError("租户成员关联的人员不存在")

        department_name: str | None = None
        if member.department_id:
            department = self.repository.get_department(member.department_id, db)
            if not department:
                raise OrganizationNotFoundError("租户成员关联的部门不存在")
            department_name = department.name

        return TenantMemberResponse(
            id=member.id,
            tenant_id=member.tenant_id,
            person_id=member.person_id,
            person_name=person.name,
            department_id=member.department_id,
            department_name=department_name,
            employee_no=member.employee_no,
            external_user_id=member.external_user_id,
            display_name=member.display_name,
            status=member.status,
            created_at=member.created_at,
            updated_at=member.updated_at,
        )

    @staticmethod
    def _commit_or_conflict(db: Session, message: str) -> None:
        """提交事务，并将数据库唯一约束错误转换为领域冲突。"""

        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise OrganizationConflictError(message) from exc

