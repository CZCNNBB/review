"""人员与组织模块 HTTP 接口集成测试。"""

import os
import unittest

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.common.db.postgres_db import get_postgres_engine
from app.main import create_app
from app.server.organization.src.models import Department, Person, TenantMember
from app.server.tenant.src.models import Tenant, TenantApiKey, TenantCallbackCredential


class OrganizationApiTestCase(unittest.TestCase):
    """验证租户、人员、部门和成员的完整管理链路。"""

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
                }
            },
        )
        SQLModel.metadata.create_all(self.engine)
        self.previous_admin_key = os.environ.get("APPROVAL_ADMIN_KEY")
        os.environ["APPROVAL_ADMIN_KEY"] = "test-admin-key"

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
        if self.previous_admin_key is None:
            os.environ.pop("APPROVAL_ADMIN_KEY", None)
        else:
            os.environ["APPROVAL_ADMIN_KEY"] = self.previous_admin_key

    def test_create_department_member_and_resolve_external_identity(self) -> None:
        """管理接口可以建立人员、部门和租户成员关系。"""

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
            f"/api/admin/tenants/{tenant_id}/departments",
            headers=self.admin_headers,
            json={"code": "finance_dept", "name": "财务部"},
        )
        self.assertEqual(department_response.status_code, 201)
        department_id = department_response.json()["data"]["id"]

        member_response = self.client.post(
            f"/api/admin/tenants/{tenant_id}/members",
            headers=self.admin_headers,
            json={
                "person_id": person_id,
                "department_id": department_id,
                "employee_no": "F001",
                "external_user_id": "project-user-001",
            },
        )
        self.assertEqual(member_response.status_code, 201)
        member_data = member_response.json()["data"]
        self.assertEqual(member_data["person_name"], "赵六")
        self.assertEqual(member_data["department_name"], "财务部")

        resolve_response = self.client.get(
            f"/api/admin/tenants/{tenant_id}/members/resolve",
            headers=self.admin_headers,
            params={"external_user_id": "project-user-001"},
        )
        self.assertEqual(resolve_response.status_code, 200)
        self.assertEqual(resolve_response.json()["data"]["id"], member_data["id"])


if __name__ == "__main__":
    unittest.main()

