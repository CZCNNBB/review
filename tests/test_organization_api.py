"""人员组织和租户绑定 HTTP 接口测试。"""

import os
import unittest

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.common.db.postgres_db import get_postgres_engine
from app.main import create_app
from app.server.organization.src.models import Department, DepartmentMember, Person
from app.server.tenant.src.models import (
    PersonBinding,
    Tenant,
    TenantApiKey,
    TenantCallbackCredential,
)


class OrganizationApiTestCase(unittest.TestCase):
    """验证业务 API 保留在 organization server 并调用 TenantScope。"""

    def setUp(self) -> None:
        """创建测试应用并替换数据库依赖。"""

        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            execution_options={
                "schema_translate_map": {
                    "tenant": None,
                    "organization": None,
                    "process": None,
                }
            },
        )
        SQLModel.metadata.create_all(self.engine)
        self.previous_admin_key = os.environ.get("APPROVAL_ADMIN_KEY")
        self.previous_tenancy_enabled = os.environ.get("TENANCY_ENABLED")
        os.environ["APPROVAL_ADMIN_KEY"] = "test-admin-key"
        os.environ["TENANCY_ENABLED"] = "true"

        app = create_app()

        def override_database_session():
            """为接口测试提供共享内存数据库会话。"""

            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_postgres_engine] = override_database_session
        self.client = TestClient(app)
        self.admin_headers = {"X-Admin-Key": "test-admin-key"}

    def tearDown(self) -> None:
        """关闭测试资源并恢复环境变量。"""

        self.client.close()
        self.engine.dispose()
        self._restore_environment("APPROVAL_ADMIN_KEY", self.previous_admin_key)
        self._restore_environment("TENANCY_ENABLED", self.previous_tenancy_enabled)

    @staticmethod
    def _restore_environment(name: str, previous_value: str | None) -> None:
        """恢复单个环境变量。"""

        if previous_value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous_value

    def test_global_resources_and_tenant_bindings(self) -> None:
        """全局资源创建后可由 organization API 绑定给租户。"""

        tenant_response = self.client.post(
            "/api/admin/tenants",
            headers=self.admin_headers,
            json={
                "code": "finance",
                "name": "财务系统",
                "callback_base_url": "https://finance.example.com/approval",
            },
        )
        self.assertEqual(tenant_response.status_code, 201)
        tenant_id = tenant_response.json()["data"]["id"]

        person_response = self.client.post(
            "/api/admin/persons",
            headers=self.admin_headers,
            json={"name": "赵六", "email": "zhaoliu@example.com"},
        )
        self.assertEqual(person_response.status_code, 201)
        person_id = person_response.json()["data"]["id"]

        department_response = self.client.post(
            "/api/admin/departments",
            headers=self.admin_headers,
            json={"code": "finance_dept", "name": "财务部"},
        )
        self.assertEqual(department_response.status_code, 201)
        bind_person_response = self.client.post(
            f"/api/admin/tenants/{tenant_id}/persons/bind",
            headers=self.admin_headers,
            json={
                "person_id": person_id,
                "employee_no": "F001",
                "external_user_id": "project-user-001",
            },
        )
        self.assertEqual(bind_person_response.status_code, 201)
        self.assertEqual(bind_person_response.json()["data"]["employee_no"], "F001")

        list_response = self.client.get(
            f"/api/admin/tenants/{tenant_id}/persons",
            headers=self.admin_headers,
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()["data"]), 1)
        self.assertEqual(list_response.json()["data"][0]["person_name"], "赵六")

    def test_global_mode_does_not_require_resource_bindings(self) -> None:
        """关闭租户能力后全局人员接口不读取绑定表。"""

        os.environ["TENANCY_ENABLED"] = "false"
        create_response = self.client.post(
            "/api/admin/persons",
            headers=self.admin_headers,
            json={"name": "全局用户"},
        )
        self.assertEqual(create_response.status_code, 201)

        list_response = self.client.get(
            "/api/admin/persons",
            headers=self.admin_headers,
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()["data"]), 1)


if __name__ == "__main__":
    unittest.main()
