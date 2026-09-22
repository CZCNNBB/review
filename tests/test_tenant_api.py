"""租户模块 HTTP 接口集成测试。"""

import os
import unittest
from uuid import UUID, uuid4

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.common.db.postgres_db import get_postgres_engine
from app.main import create_app
from app.server.tenant.api.dependencies import require_tenant_access
from app.server.tenant.src.models import PersonBinding
from app.server.tenant.src.scope import RESOURCE_PERSON


class TenantApiTestCase(unittest.TestCase):
    """验证租户创建、API Key 创建和租户上下文查询链路。"""

    def setUp(self) -> None:
        """创建内存数据库并替换 FastAPI 数据库依赖。"""

        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            # SQLite 没有 PostgreSQL Schema，测试时将 tenant 映射到默认命名空间。
            execution_options={
                "schema_translate_map": {
                    "tenant": None,
                    "organization": None,
                    "process": None,
                    "integration": None,
                }
            },
        )
        SQLModel.metadata.create_all(self.engine)
        self.previous_admin_key = os.environ.get("APPROVAL_ADMIN_KEY")
        self.previous_master_key = os.environ.get("APPROVAL_CREDENTIAL_MASTER_KEY")
        self.previous_tenancy_enabled = os.environ.get("TENANCY_ENABLED")
        os.environ["APPROVAL_ADMIN_KEY"] = "test-admin-key"
        os.environ["APPROVAL_CREDENTIAL_MASTER_KEY"] = Fernet.generate_key().decode("utf-8")
        os.environ["TENANCY_ENABLED"] = "true"

        app = create_app()

        @app.get(
            "/test/tenant-guard/persons/{person_id}",
            dependencies=[require_tenant_access(RESOURCE_PERSON, "person_id")],
        )
        def get_guarded_person(person_id: str) -> dict[str, str]:
            """提供仅用于测试通用租户访问守卫的受保护接口。"""

            return {"person_id": person_id}

        def override_database_session():
            """为接口测试提供共享内存数据库会话。"""

            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_postgres_engine] = override_database_session
        self.client = TestClient(app)

    def tearDown(self) -> None:
        """关闭测试客户端并恢复环境变量。"""

        self.client.close()
        self.engine.dispose()
        self._restore_environment("APPROVAL_ADMIN_KEY", self.previous_admin_key)
        self._restore_environment(
            "APPROVAL_CREDENTIAL_MASTER_KEY",
            self.previous_master_key,
        )
        self._restore_environment("TENANCY_ENABLED", self.previous_tenancy_enabled)

    @staticmethod
    def _restore_environment(name: str, previous_value: str | None) -> None:
        """恢复单个环境变量在测试前的值。"""

        if previous_value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous_value

    def test_create_key_and_query_tenant_context(self) -> None:
        """创建的 API Key 可以访问租户上下文，并能从管理列表再次查看。"""

        admin_headers = {"X-Admin-Key": "test-admin-key"}
        tenant_response = self.client.post(
            "/api/admin/tenants",
            headers=admin_headers,
            json={
                "code": "finance",
                "name": "财务系统",
                "callback_base_url": "https://finance.example.com/internal/approval",
            },
        )
        self.assertEqual(tenant_response.status_code, 201)
        tenant_id = tenant_response.json()["data"]["id"]

        key_response = self.client.post(
            f"/api/admin/tenants/{tenant_id}/api-keys",
            headers=admin_headers,
            json={"name": "测试主 Key"},
        )
        self.assertEqual(key_response.status_code, 201)
        plaintext_api_key = key_response.json()["data"]["api_key"]

        context_response = self.client.get(
            "/api/tenant/context",
            headers={"X-API-Key": plaintext_api_key},
        )
        self.assertEqual(context_response.status_code, 200)
        self.assertEqual(context_response.json()["data"]["tenant_id"], tenant_id)
        self.assertEqual(context_response.json()["data"]["tenant_code"], "FINANCE")

        list_response = self.client.get(
            f"/api/admin/tenants/{tenant_id}/api-keys",
            headers=admin_headers,
        )
        self.assertEqual(list_response.status_code, 200)
        listed_api_key = list_response.json()["data"][0]["api_key"]
        self.assertEqual(listed_api_key, plaintext_api_key)

    def test_tenant_access_guard_allows_bound_resource_and_rejects_other_resource(self) -> None:
        """通用访问守卫只允许当前租户访问已启用的资源绑定。"""

        admin_headers = {"X-Admin-Key": "test-admin-key"}
        tenant_response = self.client.post(
            "/api/admin/tenants",
            headers=admin_headers,
            json={
                "code": "guard_test",
                "name": "访问守卫测试租户",
                "callback_base_url": "https://guard.example.com/callback",
            },
        )
        tenant_id = tenant_response.json()["data"]["id"]

        key_response = self.client.post(
            f"/api/admin/tenants/{tenant_id}/api-keys",
            headers=admin_headers,
            json={"name": "访问守卫测试 Key"},
        )
        plaintext_api_key = key_response.json()["data"]["api_key"]
        allowed_person_id = uuid4()
        denied_person_id = uuid4()

        # 访问守卫只依赖 tenant Schema 中的绑定关系，不要求业务资源表保存 tenant_id。
        with Session(self.engine) as db:
            db.add(
                PersonBinding(
                    tenant_id=UUID(tenant_id),
                    person_id=allowed_person_id,
                    status="ENABLED",
                )
            )
            db.commit()

        request_headers = {"X-API-Key": plaintext_api_key}
        allowed_response = self.client.get(
            f"/test/tenant-guard/persons/{allowed_person_id}",
            headers=request_headers,
        )
        denied_response = self.client.get(
            f"/test/tenant-guard/persons/{denied_person_id}",
            headers=request_headers,
        )

        self.assertEqual(allowed_response.status_code, 200)
        self.assertEqual(denied_response.status_code, 403)

    def test_callback_credential_never_returns_the_service_token(self) -> None:
        """配置 Service Token 时只返回凭据元数据，不回显 Token 明文。"""

        admin_headers = {"X-Admin-Key": "test-admin-key"}
        tenant_response = self.client.post(
            "/api/admin/tenants",
            headers=admin_headers,
            json={
                "code": "callback_secret",
                "name": "回调凭据测试租户",
                "callback_base_url": "https://callback.example.com/internal",
            },
        )
        tenant_id = tenant_response.json()["data"]["id"]
        service_token = "service_token_never_returned"

        create_response = self.client.post(
            f"/api/admin/tenants/{tenant_id}/callback-credentials",
            headers=admin_headers,
            json={
                "name": "生产环境回调",
                "token": service_token,
                "header_name": "X-Service-Token",
                "token_prefix": "",
            },
        )

        self.assertEqual(create_response.status_code, 201, create_response.text)
        created = create_response.json()["data"]
        self.assertEqual(created["header_name"], "X-Service-Token")
        self.assertEqual(created["token_prefix"], "")
        self.assertEqual(created["status"], "ACTIVE")
        self.assertNotIn(service_token, create_response.text)
        self.assertNotIn("token_ciphertext", created)

        list_response = self.client.get(
            f"/api/admin/tenants/{tenant_id}/callback-credentials",
            headers=admin_headers,
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertNotIn(service_token, list_response.text)

    def test_replacing_callback_credential_revokes_previous(self) -> None:
        """一个租户同时只保留一个有效凭据，替换 Token 时旧凭据被撤销。"""

        admin_headers = {"X-Admin-Key": "test-admin-key"}
        tenant_response = self.client.post(
            "/api/admin/tenants",
            headers=admin_headers,
            json={
                "code": "credential_replace",
                "name": "凭据替换测试租户",
                "callback_base_url": "https://replace.example.com/internal",
            },
        )
        tenant_id = tenant_response.json()["data"]["id"]

        first_response = self.client.post(
            f"/api/admin/tenants/{tenant_id}/callback-credentials",
            headers=admin_headers,
            json={"name": "第一版", "token": "first_token"},
        )
        self.assertEqual(first_response.status_code, 201, first_response.text)
        first_credential_id = first_response.json()["data"]["id"]

        second_response = self.client.post(
            f"/api/admin/tenants/{tenant_id}/callback-credentials",
            headers=admin_headers,
            json={"name": "第二版", "token": "second_token"},
        )
        self.assertEqual(second_response.status_code, 201, second_response.text)

        credentials = self.client.get(
            f"/api/admin/tenants/{tenant_id}/callback-credentials",
            headers=admin_headers,
        ).json()["data"]
        statuses = {item["id"]: item["status"] for item in credentials}
        self.assertEqual(statuses[first_credential_id], "REVOKED")
        self.assertEqual(
            [item["status"] for item in credentials].count("ACTIVE"),
            1,
        )

        # 默认请求头为 Authorization，前缀为 Bearer。
        active_credential = next(
            item for item in credentials if item["status"] == "ACTIVE"
        )
        self.assertEqual(active_credential["header_name"], "Authorization")
        self.assertEqual(active_credential["token_prefix"], "Bearer")

    def test_invalid_callback_credential_request_is_rejected(self) -> None:
        """请求头名称不合法或 Token 为空时接口直接拒绝。"""

        admin_headers = {"X-Admin-Key": "test-admin-key"}
        tenant_response = self.client.post(
            "/api/admin/tenants",
            headers=admin_headers,
            json={
                "code": "credential_invalid",
                "name": "凭据校验测试租户",
                "callback_base_url": "https://invalid.example.com/internal",
            },
        )
        tenant_id = tenant_response.json()["data"]["id"]

        invalid_header = self.client.post(
            f"/api/admin/tenants/{tenant_id}/callback-credentials",
            headers=admin_headers,
            json={"name": "非法请求头", "token": "abc", "header_name": "Bad Header"},
        )
        empty_token = self.client.post(
            f"/api/admin/tenants/{tenant_id}/callback-credentials",
            headers=admin_headers,
            json={"name": "空 Token", "token": "   "},
        )

        self.assertEqual(invalid_header.status_code, 422)
        self.assertEqual(empty_token.status_code, 422)

    def test_tenant_access_guard_is_no_op_in_global_mode(self) -> None:
        """关闭租户能力后，访问守卫不要求 API Key 或资源绑定。"""

        os.environ["TENANCY_ENABLED"] = "false"
        response = self.client.get(f"/test/tenant-guard/persons/{uuid4()}")

        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
