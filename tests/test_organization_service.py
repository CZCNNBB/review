"""人员组织核心能力与租户作用域测试。"""

import os
import unittest

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.common.scope import GlobalResourceScope
from app.server.tenant.api.dependencies import build_resource_scope_dependency
from app.server.organization.src.models import Department, DepartmentMember, Person
from app.server.organization.src.schemas.organization_schema import (
    DepartmentCreateRequest,
    PersonCreateRequest,
)
from app.server.organization.src.service.organization_service import OrganizationService
from app.server.tenant.src.models import (
    PersonBinding,
    Tenant,
    TenantApiKey,
    TenantCallbackCredential,
)
from app.server.tenant.src.schemas.tenant_schema import TenantCreateRequest
from app.server.tenant.src.scope.tenant_scope import (
    RESOURCE_PERSON,
    TenantResourceAccessError,
    TenantResourceScope,
    create_resource_scope,
)
from app.server.tenant.src.service.tenant_service import TenantService


class OrganizationServiceTestCase(unittest.TestCase):
    """验证核心组织数据与可选租户作用域相互独立。"""

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
        self.organization_service = OrganizationService()
        self.tenant_service = TenantService()
        self.previous_tenancy_enabled = os.environ.get("TENANCY_ENABLED")
        os.environ["TENANCY_ENABLED"] = "true"

    def tearDown(self) -> None:
        """关闭数据库资源并恢复租户开关。"""

        self.db.close()
        self.engine.dispose()
        if self.previous_tenancy_enabled is None:
            os.environ.pop("TENANCY_ENABLED", None)
        else:
            os.environ["TENANCY_ENABLED"] = self.previous_tenancy_enabled

    def test_global_mode_lists_resources_without_tenant_tables(self) -> None:
        """全局作用域不需要人员租户绑定即可查询人员和部门。"""

        person = self.organization_service.create_person(
            PersonCreateRequest(name="张三"),
            self.db,
        )
        department = self.organization_service.create_department(
            DepartmentCreateRequest(code="FINANCE", name="财务部"),
            self.db,
        )

        persons = self.organization_service.list_persons(
            self.db,
            scope=GlobalResourceScope(),
        )
        departments = self.organization_service.list_departments(
            self.db,
            scope=GlobalResourceScope(),
        )

        self.assertEqual([item.id for item in persons], [person.id])
        self.assertEqual([item.id for item in departments], [department.id])

    def test_tenant_scope_filters_and_checks_person_access(self) -> None:
        """租户作用域只返回当前租户已经绑定的人员。"""

        tenant = self.tenant_service.create_tenant(
            TenantCreateRequest(
                code="FINANCE",
                name="财务系统",
                callback_base_url="https://finance.example.com/approval",
            ),
            self.db,
        )
        visible_person = self.organization_service.create_person(
            PersonCreateRequest(name="李四"),
            self.db,
        )
        hidden_person = self.organization_service.create_person(
            PersonCreateRequest(name="王五"),
            self.db,
        )
        scope = create_resource_scope(RESOURCE_PERSON, tenant.id)
        scope.bind(
            visible_person.id,
            self.db,
            attributes={"external_user_id": "platform-user-001"},
        )
        self.db.commit()

        persons = self.organization_service.list_persons(self.db, scope=scope)
        self.assertEqual([item.id for item in persons], [visible_person.id])
        scope.require_access(visible_person.id, self.db)
        with self.assertRaises(TenantResourceAccessError):
            scope.require_access(hidden_person.id, self.db)

    def test_department_membership_is_independent_from_tenant(self) -> None:
        """人员部门关系可以在不创建租户的情况下正常使用。"""

        person = self.organization_service.create_person(
            PersonCreateRequest(name="赵六"),
            self.db,
        )
        department = self.organization_service.create_department(
            DepartmentCreateRequest(code="LEGAL", name="法务部"),
            self.db,
        )

        response = self.organization_service.add_department_member(
            department.id,
            person.id,
            self.db,
        )
        self.assertEqual(response.person_name, "赵六")
        self.assertEqual(response.department_name, "法务部")

    def test_fastapi_scope_dependency_switches_with_tenancy_setting(self) -> None:
        """统一依赖在租户模式校验 API Key，在全局模式不要求 API Key。"""

        tenant = self.tenant_service.create_tenant(
            TenantCreateRequest(
                code="PAYMENT",
                name="付款系统",
                callback_base_url="https://payment.example.com/approval",
            ),
            self.db,
        )
        api_key = self.tenant_service.create_api_key(
            tenant_id=tenant.id,
            name="测试 Key",
            expires_at=None,
            db=self.db,
        )
        dependency = build_resource_scope_dependency(RESOURCE_PERSON)

        tenant_scope = dependency(x_api_key=api_key.api_key, db=self.db)
        self.assertIsInstance(tenant_scope, TenantResourceScope)
        self.assertEqual(tenant_scope.tenant_id, tenant.id)

        # 关闭租户能力后，同一个依赖直接返回全局作用域且不读取 API Key。
        os.environ["TENANCY_ENABLED"] = "false"
        global_scope = dependency(x_api_key=None, db=self.db)
        self.assertIsInstance(global_scope, GlobalResourceScope)


if __name__ == "__main__":
    unittest.main()
