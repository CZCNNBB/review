"""人员与组织模块数据访问实现。"""

from uuid import UUID

from sqlmodel import Session, select

from app.server.organization.src.models.organization_model import (
    Department,
    Person,
    TenantMember,
)


class OrganizationRepository:
    """封装人员、部门和租户成员数据库查询。"""

    def add(self, entity: Person | Department | TenantMember, db: Session) -> None:
        """将人员组织实体加入当前数据库事务。"""

        db.add(entity)

    def get_person(self, person_id: UUID, db: Session) -> Person | None:
        """按主键查询全局人员。"""

        return db.get(Person, person_id)

    def list_persons(self, db: Session, offset: int, limit: int) -> list[Person]:
        """按创建时间倒序分页查询全局人员。"""

        statement = select(Person).order_by(Person.created_at.desc()).offset(offset).limit(limit)
        return list(db.exec(statement).all())

    def get_department(self, department_id: UUID, db: Session) -> Department | None:
        """按主键查询部门。"""

        return db.get(Department, department_id)

    def get_department_by_code(
        self,
        tenant_id: UUID,
        code: str,
        db: Session,
    ) -> Department | None:
        """按租户和编码查询部门。"""

        statement = select(Department).where(
            Department.tenant_id == tenant_id,
            Department.code == code,
        )
        return db.exec(statement).first()

    def list_departments(self, tenant_id: UUID, db: Session) -> list[Department]:
        """查询租户下的全部平铺部门。"""

        statement = (
            select(Department)
            .where(Department.tenant_id == tenant_id)
            .order_by(Department.created_at.desc())
        )
        return list(db.exec(statement).all())

    def get_member(self, member_id: UUID, db: Session) -> TenantMember | None:
        """按主键查询租户成员。"""

        return db.get(TenantMember, member_id)

    def get_member_by_person(
        self,
        tenant_id: UUID,
        person_id: UUID,
        db: Session,
    ) -> TenantMember | None:
        """按租户和人员查询成员关系。"""

        statement = select(TenantMember).where(
            TenantMember.tenant_id == tenant_id,
            TenantMember.person_id == person_id,
        )
        return db.exec(statement).first()

    def get_member_by_external_user_id(
        self,
        tenant_id: UUID,
        external_user_id: str,
        db: Session,
    ) -> TenantMember | None:
        """按租户和项目平台用户标识查询成员。"""

        statement = select(TenantMember).where(
            TenantMember.tenant_id == tenant_id,
            TenantMember.external_user_id == external_user_id,
        )
        return db.exec(statement).first()

    def list_members(self, tenant_id: UUID, db: Session) -> list[TenantMember]:
        """查询租户下的全部成员。"""

        statement = (
            select(TenantMember)
            .where(TenantMember.tenant_id == tenant_id)
            .order_by(TenantMember.created_at.desc())
        )
        return list(db.exec(statement).all())

