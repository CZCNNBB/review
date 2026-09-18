"""租户模块 HTTP 接口集成测试。"""

import os
import unittest

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.common.db.postgres_db import get_postgres_engine
from app.main import create_app


class TenantApiTestCase(unittest.TestCase):
    """验证租户创建、API Key 创建和租户上下文查询链路。"""

    def setUp(self) -> None:
        """创建内存数据库并替换 FastAPI 数据库依赖。"""

        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            # SQLite 没有 PostgreSQL Schema，测试时将 tenant 映射到默认命名空间。
            execution_options={"schema_translate_map": {"tenant": None}},
        )
        SQLModel.metadata.create_all(self.engine)
        self.previous_admin_key = os.environ.get("APPROVAL_ADMIN_KEY")
        self.previous_master_key = os.environ.get("APPROVAL_CREDENTIAL_MASTER_KEY")
        os.environ["APPROVAL_ADMIN_KEY"] = "test-admin-key"
        os.environ["APPROVAL_CREDENTIAL_MASTER_KEY"] = Fernet.generate_key().decode("utf-8")

        app = create_app()

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


if __name__ == "__main__":
    unittest.main()
