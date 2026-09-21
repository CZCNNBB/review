"""人员与组织模块数据访问实现。"""

from uuid import UUID

from sqlmodel import Session, select

from app.common.scope import ResourceScope
from app.server.organization.src.models.organization_model import (
    Department,
    DepartmentMember,
    Person,
)


class OrganizationRepository:
    """封装全局人员、部门和人员部门关系查询。"""

    def add(self, entity: Person | Department | DepartmentMember, db: Session) -> None:
        """将人员组织实体加入当前数据库事务。"""

        db.add(entity)

    def get_person(self, person_id: UUID, db: Session) -> Person | None:
        """按主键查询全局人员。"""

        return db.get(Person, person_id)

    def list_persons(
        self,
        db: Session,
        scope: ResourceScope,
        offset: int,
        limit: int,
    ) -> list[Person]:
        """按照给定资源作用域分页查询人员。"""

        statement = select(Person).order_by(Person.created_at.desc())
        statement = scope.apply_filter(statement, Person.id)
        statement = statement.offset(offset).limit(limit)
        return list(db.exec(statement).all())

    def list_persons_by_ids(
        self,
        person_ids: list[UUID],
        db: Session,
    ) -> list[Person]:
        """批量按主键查询人员，供其它模块校验人员引用时一次性取回。

        这里不做租户作用域过滤：人员是否可用由调用方按业务规则判断。
        """

        if not person_ids:
            return []

        statement = select(Person).where(Person.id.in_(person_ids))
        return list(db.exec(statement).all())

    def get_department(self, department_id: UUID, db: Session) -> Department | None:
        """按主键查询全局部门。"""

        return db.get(Department, department_id)

    def get_department_by_code(self, code: str, db: Session) -> Department | None:
        """按全局编码查询部门。"""

        statement = select(Department).where(Department.code == code)
        return db.exec(statement).first()

    def list_departments(
        self,
        db: Session,
        scope: ResourceScope,
        offset: int,
        limit: int,
    ) -> list[Department]:
        """按照给定资源作用域分页查询部门。"""

        statement = select(Department).order_by(Department.created_at.desc())
        statement = scope.apply_filter(statement, Department.id)
        statement = statement.offset(offset).limit(limit)
        return list(db.exec(statement).all())

    def get_department_member(
        self,
        department_id: UUID,
        person_id: UUID,
        db: Session,
    ) -> DepartmentMember | None:
        """查询指定人员部门关系。"""

        statement = select(DepartmentMember).where(
            DepartmentMember.department_id == department_id,
            DepartmentMember.person_id == person_id,
        )
        return db.exec(statement).first()

    def list_department_members(
        self,
        department_id: UUID,
        db: Session,
    ) -> list[DepartmentMember]:
        """查询部门下的全部人员关系。"""

        statement = (
            select(DepartmentMember)
            .where(DepartmentMember.department_id == department_id)
            .order_by(DepartmentMember.created_at.desc())
        )
        return list(db.exec(statement).all())

