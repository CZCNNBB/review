"""全局人员、部门和人员部门关系业务逻辑。"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.common.scope import ResourceScope
from app.server.organization.src.models.organization_model import (
    Department,
    DepartmentMember,
    Person,
)
from app.server.organization.src.repository.organization_repository import OrganizationRepository
from app.server.organization.src.schemas.organization_schema import (
    DepartmentCreateRequest,
    DepartmentMemberResponse,
    DepartmentUpdateRequest,
    PersonCreateRequest,
    PersonUpdateRequest,
)
from app.server.organization.src.service.exceptions import (
    OrganizationConflictError,
    OrganizationNotFoundError,
    OrganizationValidationError,
)


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""

    return datetime.now(timezone.utc)


class OrganizationService:
    """提供与租户无关的人员和部门业务能力。"""

    def __init__(self, repository: OrganizationRepository | None = None):
        """初始化人员组织服务。"""

        self.repository = repository or OrganizationRepository()

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

    def list_persons(
        self,
        db: Session,
        scope: ResourceScope,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Person]:
        """按照资源作用域分页查询人员。"""

        return self.repository.list_persons(
            db,
            scope=scope,
            offset=offset,
            limit=limit,
        )

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
        request: DepartmentCreateRequest,
        db: Session,
    ) -> Department:
        """创建与租户无关的全局部门。"""

        existing_department = self.repository.get_department_by_code(request.code, db)
        if existing_department:
            raise OrganizationConflictError(f"部门编码 {request.code} 已存在")

        department = Department(code=request.code, name=request.name)
        self.repository.add(department, db)
        self._commit_or_conflict(db, "部门编码已存在")
        db.refresh(department)
        return department

    def list_departments(
        self,
        db: Session,
        scope: ResourceScope,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Department]:
        """按照资源作用域分页查询部门。"""

        return self.repository.list_departments(
            db,
            scope=scope,
            offset=offset,
            limit=limit,
        )

    def get_department(self, department_id: UUID, db: Session) -> Department:
        """查询全局部门。"""

        department = self.repository.get_department(department_id, db)
        if not department:
            raise OrganizationNotFoundError("部门不存在")
        return department

    def update_department(
        self,
        department_id: UUID,
        request: DepartmentUpdateRequest,
        db: Session,
    ) -> Department:
        """更新部门名称或启停状态。"""

        department = self.get_department(department_id, db)
        update_data = request.model_dump(exclude_unset=True)
        for field_name, field_value in update_data.items():
            setattr(department, field_name, field_value)

        department.updated_at = utc_now()
        self.repository.add(department, db)
        self._commit_or_conflict(db, "部门信息冲突")
        db.refresh(department)
        return department

    def add_department_member(
        self,
        department_id: UUID,
        person_id: UUID,
        db: Session,
    ) -> DepartmentMemberResponse:
        """把启用人员加入启用部门。"""

        department = self.get_department(department_id, db)
        person = self.get_person(person_id, db)
        if department.status != "ENABLED":
            raise OrganizationValidationError("已停用部门不能添加人员")
        if person.status != "ENABLED":
            raise OrganizationValidationError("已停用人员不能加入部门")

        existing_member = self.repository.get_department_member(
            department_id,
            person_id,
            db,
        )
        if existing_member:
            if existing_member.status == "DISABLED":
                existing_member.status = "ENABLED"
                existing_member.updated_at = utc_now()
                self.repository.add(existing_member, db)
                self._commit_or_conflict(db, "人员部门关系冲突")
                db.refresh(existing_member)
                return self._build_department_member_response(
                    existing_member,
                    department,
                    person,
                )
            raise OrganizationConflictError("人员已经在当前部门中")

        member = DepartmentMember(
            department_id=department_id,
            person_id=person_id,
        )
        self.repository.add(member, db)
        self._commit_or_conflict(db, "人员已经在当前部门中")
        db.refresh(member)
        return self._build_department_member_response(member, department, person)

    def list_department_members(
        self,
        department_id: UUID,
        db: Session,
    ) -> list[DepartmentMemberResponse]:
        """查询部门人员并补充人员、部门名称。"""

        department = self.get_department(department_id, db)
        members = self.repository.list_department_members(department_id, db)
        responses: list[DepartmentMemberResponse] = []
        for member in members:
            person = self.get_person(member.person_id, db)
            responses.append(
                self._build_department_member_response(member, department, person)
            )
        return responses

    def disable_department_member(
        self,
        department_id: UUID,
        person_id: UUID,
        db: Session,
    ) -> DepartmentMemberResponse:
        """停用指定人员部门关系。"""

        department = self.get_department(department_id, db)
        person = self.get_person(person_id, db)
        member = self.repository.get_department_member(department_id, person_id, db)
        if not member:
            raise OrganizationNotFoundError("人员部门关系不存在")

        member.status = "DISABLED"
        member.updated_at = utc_now()
        self.repository.add(member, db)
        db.commit()
        db.refresh(member)
        return self._build_department_member_response(member, department, person)

    @staticmethod
    def _build_department_member_response(
        member: DepartmentMember,
        department: Department,
        person: Person,
    ) -> DepartmentMemberResponse:
        """构造带人员和部门名称的关系响应。"""

        return DepartmentMemberResponse(
            id=member.id,
            department_id=department.id,
            department_name=department.name,
            person_id=person.id,
            person_name=person.name,
            status=member.status,
            created_at=member.created_at,
            updated_at=member.updated_at,
        )

    @staticmethod
    def _commit_or_conflict(db: Session, message: str) -> None:
        """提交事务，并将唯一约束错误转换为领域冲突。"""

        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise OrganizationConflictError(message) from exc

