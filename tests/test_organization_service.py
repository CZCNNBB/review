"""人员与组织模块业务规则测试。"""

import unittest

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.server.organization.src.models import Department, Person, TenantMember
from app.server.organization.src.schemas.organization_schema import (
    DepartmentCreateRequest,
    PersonCreateRequest,
    TenantMemberCreateRequest,
)
from app.server.organization.src.service.exceptions import (
    OrganizationConflictError,
    OrganizationNotFoundError,
)
from app.server.organization.src.service.organization_service import OrganizationService
from app.server.tenant.src.models import Tenant, TenantApiKey, TenantCallbackCredential
from app.server.tenant.src.schemas.tenant_schema import TenantCreateRequest
from app.server.tenant.src.service.tenant_service import TenantService


class OrganizationServiceTestCase(unittest.TestCase):
    """验证人员、部门和租户成员的隔离与唯一性规则。"""

    def setUp(self) -> None:
        """创建支持多 Schema 映射的 SQLite 内存数据库。"""

        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            execution_options={
                "schema_translate_map": {
                    "tenant": None,
                    "organization": None,
                }
            },
        )
        SQLModel.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.tenant_service = TenantService()
        self.organization_service = OrganizationService()

    def tearDown(self) -> None:
        """关闭测试数据库资源。"""

        self.db.close()
        self.engine.dispose()

    def create_tenant(self, code: str, name: str) -> Tenant:
        """创建测试使用的业务系统租户。"""

        return self.tenant_service.create_tenant(
            TenantCreateRequest(
                code=code,
                name=name,
                callback_base_url=f"https://{code.lower()}.example.com/approval",
            ),
            self.db,
        )

    def test_person_can_join_multiple_tenants_and_resolve_external_identity(self) -> None:
        """同一人员可加入多个租户，并按租户解析外部用户标识。"""

        finance_tenant = self.create_tenant("FINANCE", "财务系统")
        contract_tenant = self.create_tenant("CONTRACT", "合同系统")
        person = self.organization_service.create_person(
            PersonCreateRequest(name="张三", email="ZHANGSAN@EXAMPLE.COM"),
            self.db,
        )

        finance_member = self.organization_service.create_member(
            finance_tenant.id,
            TenantMemberCreateRequest(
                person_id=person.id,
                employee_no="F001",
                external_user_id="platform-user-001",
            ),
            self.db,
        )
        contract_member = self.organization_service.create_member(
            contract_tenant.id,
            TenantMemberCreateRequest(
                person_id=person.id,
                employee_no="C001",
                external_user_id="platform-user-001",
            ),
            self.db,
        )

        resolved_member = self.organization_service.resolve_member_by_external_user_id(
            finance_tenant.id,
            "platform-user-001",
            self.db,
        )
        self.assertEqual(resolved_member.id, finance_member.id)
        self.assertNotEqual(finance_member.id, contract_member.id)
        self.assertEqual(resolved_member.person_name, "张三")
        self.assertEqual(person.email, "zhangsan@example.com")

    def test_member_cannot_bind_department_from_another_tenant(self) -> None:
        """租户成员不能绑定另一个租户的部门。"""

        finance_tenant = self.create_tenant("FINANCE", "财务系统")
        contract_tenant = self.create_tenant("CONTRACT", "合同系统")
        contract_department = self.organization_service.create_department(
            contract_tenant.id,
            DepartmentCreateRequest(code="LEGAL", name="法务部"),
            self.db,
        )
        person = self.organization_service.create_person(
            PersonCreateRequest(name="李四"),
            self.db,
        )

        with self.assertRaises(OrganizationNotFoundError):
            self.organization_service.create_member(
                finance_tenant.id,
                TenantMemberCreateRequest(
                    person_id=person.id,
                    department_id=contract_department.id,
                ),
                self.db,
            )

    def test_person_cannot_join_same_tenant_twice(self) -> None:
        """同一人员在同一租户中只能存在一个成员关系。"""

        tenant = self.create_tenant("FINANCE", "财务系统")
        person = self.organization_service.create_person(
            PersonCreateRequest(name="王五"),
            self.db,
        )
        request = TenantMemberCreateRequest(person_id=person.id)
        self.organization_service.create_member(tenant.id, request, self.db)

        with self.assertRaises(OrganizationConflictError):
            self.organization_service.create_member(tenant.id, request, self.db)


if __name__ == "__main__":
    unittest.main()

