"""业务执行记录查询接口测试。

接口供后台人员核对审批通过后业务系统是否真的被调用。响应中不能出现 Service Token、
密文或完整认证请求头。
"""

import os
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.common.db.postgres_db import get_postgres_engine
from app.main import create_app
from app.server.integration.src.models.business_action_model import BusinessAction
from app.server.process.src.constants import (
    EXECUTION_STATUS_FAILED,
    EXECUTION_STATUS_PENDING,
    EXECUTION_STATUS_SUCCEEDED,
)
from app.server.process.src.models.approval_model import ApprovalInstance
from app.server.process.src.models.execution_model import BusinessExecutionRecord
from app.server.tenant.src.schemas.tenant_schema import TenantCreateRequest
from app.server.tenant.src.service.tenant_service import TenantService


ADMIN_KEY = "execution-api-admin-key"
SERVICE_TOKEN = "service_token_api_secret_value"


class ExecutionRecordApiTestCase(unittest.TestCase):
    """验证执行记录列表、详情、筛选和敏感信息边界。"""

    def setUp(self) -> None:
        """创建内存数据库并准备测试客户端。"""

        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
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
        os.environ["APPROVAL_ADMIN_KEY"] = ADMIN_KEY
        os.environ["APPROVAL_CREDENTIAL_MASTER_KEY"] = Fernet.generate_key().decode(
            "utf-8"
        )
        os.environ["TENANCY_ENABLED"] = "true"

        app = create_app()
        self._engine = self.engine

        def override_database_session():
            """为接口测试提供共享内存数据库会话。"""

            with Session(self._engine) as db:
                yield db

        app.dependency_overrides[get_postgres_engine] = override_database_session
        self.client = TestClient(app)
        self.admin_headers = {"X-Admin-Key": ADMIN_KEY}

    def tearDown(self) -> None:
        """关闭客户端并恢复环境变量。"""

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

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def create_record(
        self,
        action_code: str = "PAYMENT_EXECUTE",
        status: str = EXECUTION_STATUS_PENDING,
        http_status_code: int | None = None,
        response_body: str | None = None,
        error_message: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        with_action: bool = True,
    ) -> BusinessExecutionRecord:
        """创建一条执行记录。"""

        with Session(self.engine) as db:
            action_id = None
            if with_action:
                action = BusinessAction(
                    action_code=action_code,
                    name="付款执行",
                    http_method="POST",
                    relative_path="/payment/execute",
                    success_status_codes_json=[200, 202],
                    timeout_ms=5000,
                )
                db.add(action)
                db.commit()
                action_id = action.id

            instance = ApprovalInstance(
                process_id=uuid4(),
                process_version_id=uuid4(),
                business_key=f"BIZ-{uuid4().hex[:8]}",
                idempotency_key=f"KEY-{uuid4().hex[:8]}",
                title="供应商付款申请",
                action_code=action_code,
                status="APPROVED",
            )
            db.add(instance)
            db.commit()

            record = BusinessExecutionRecord(
                approval_instance_id=instance.id,
                business_action_id=action_id,
                action_code=action_code,
                http_method="POST" if with_action else None,
                relative_path="/payment/execute" if with_action else None,
                success_status_codes_json=[200, 202] if with_action else None,
                timeout_ms=5000 if with_action else None,
                request_payload_json={"payment_id": "PAY-001", "amount": 100},
                status=status,
                http_status_code=http_status_code,
                response_body=response_body,
                error_message=error_message,
                started_at=started_at,
                finished_at=finished_at,
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            return record

    # ------------------------------------------------------------------
    # 列表与详情
    # ------------------------------------------------------------------

    def test_list_returns_records_with_duration(self) -> None:
        """列表返回执行记录，耗时由起止时间计算。"""

        start_time = datetime.now(timezone.utc) - timedelta(seconds=3)
        record = self.create_record(
            status=EXECUTION_STATUS_SUCCEEDED,
            http_status_code=200,
            response_body='{"ok": true}',
            started_at=start_time,
            finished_at=start_time + timedelta(milliseconds=1500),
        )

        response = self.client.get(
            "/api/admin/execution-records",
            headers=self.admin_headers,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(len(payload), 1)
        item = payload[0]
        self.assertEqual(item["id"], str(record.id))
        self.assertEqual(item["approval_instance_id"], str(record.approval_instance_id))
        self.assertEqual(item["action_code"], "PAYMENT_EXECUTE")
        self.assertEqual(item["status"], EXECUTION_STATUS_SUCCEEDED)
        self.assertEqual(item["http_status_code"], 200)
        self.assertEqual(item["duration_ms"], 1500)
        # 列表项不返回响应正文和请求参数，避免列表页一次加载过多数据。
        self.assertNotIn("response_body", item)
        self.assertNotIn("request_payload", item)

    def test_detail_returns_snapshot_and_response(self) -> None:
        """详情返回动作配置快照、请求参数和截断后的响应正文。"""

        record = self.create_record(
            status=EXECUTION_STATUS_FAILED,
            http_status_code=500,
            response_body="business failure",
            error_message="业务系统返回状态码 500，不符合成功状态码规则",
        )

        response = self.client.get(
            f"/api/admin/execution-records/{record.id}",
            headers=self.admin_headers,
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["id"], str(record.id))
        self.assertEqual(data["business_action_id"], str(record.business_action_id))
        self.assertEqual(data["http_method"], "POST")
        self.assertEqual(data["relative_path"], "/payment/execute")
        self.assertEqual(data["timeout_ms"], 5000)
        self.assertEqual(data["success_status_codes"], [200, 202])
        self.assertEqual(
            data["request_payload"],
            {"payment_id": "PAY-001", "amount": 100},
        )
        self.assertEqual(data["response_body"], "business failure")
        self.assertIn("500", data["error_message"])

    def test_list_filters_by_instance_action_and_status(self) -> None:
        """列表支持按审批实例、业务动作和执行状态筛选。"""

        payment_record = self.create_record(action_code="PAYMENT_EXECUTE")
        self.create_record(
            action_code="ORDER_CONFIRM",
            status=EXECUTION_STATUS_FAILED,
            with_action=False,
        )

        by_instance = self.client.get(
            "/api/admin/execution-records",
            params={"approval_instance_id": str(payment_record.approval_instance_id)},
            headers=self.admin_headers,
        )
        self.assertEqual(len(by_instance.json()["data"]), 1)

        by_action = self.client.get(
            "/api/admin/execution-records",
            params={"action_code": "ORDER_CONFIRM"},
            headers=self.admin_headers,
        )
        self.assertEqual(len(by_action.json()["data"]), 1)
        self.assertEqual(by_action.json()["data"][0]["action_code"], "ORDER_CONFIRM")

        by_status = self.client.get(
            "/api/admin/execution-records",
            params={"status": EXECUTION_STATUS_FAILED},
            headers=self.admin_headers,
        )
        self.assertEqual(len(by_status.json()["data"]), 1)

        self.assertEqual(
            self.client.get(
                "/api/admin/execution-records",
                params={"status": EXECUTION_STATUS_SUCCEEDED},
                headers=self.admin_headers,
            ).json()["data"],
            [],
        )

    def test_invalid_status_filter_is_rejected(self) -> None:
        """状态筛选值由接口约束，非法取值直接拒绝。"""

        response = self.client.get(
            "/api/admin/execution-records",
            params={"status": "DONE"},
            headers=self.admin_headers,
        )

        self.assertEqual(response.status_code, 422)

    def test_unknown_record_returns_not_found(self) -> None:
        """查询不存在的执行记录返回 404。"""

        response = self.client.get(
            f"/api/admin/execution-records/{uuid4()}",
            headers=self.admin_headers,
        )

        self.assertEqual(response.status_code, 404)

    def test_admin_key_is_required(self) -> None:
        """缺少或错误的管理密钥不能查询执行记录。"""

        no_key = self.client.get("/api/admin/execution-records")
        wrong_key = self.client.get(
            "/api/admin/execution-records",
            headers={"X-Admin-Key": "wrong-key"},
        )

        self.assertEqual(no_key.status_code, 401)
        self.assertEqual(wrong_key.status_code, 401)

    # ------------------------------------------------------------------
    # 敏感信息
    # ------------------------------------------------------------------

    def test_service_token_never_appears_in_responses(self) -> None:
        """配置了 Service Token 后，任何查询响应都不能带出 Token 或密文。"""

        tenant_service = TenantService()
        with Session(self.engine) as db:
            tenant = tenant_service.create_tenant(
                TenantCreateRequest(
                    code="finance",
                    name="财务系统",
                    callback_base_url="https://finance.example.com/internal/approval",
                ),
                db,
            )
            credential = tenant_service.create_callback_credential(
                tenant_id=tenant.id,
                name="生产环境回调",
                token=SERVICE_TOKEN,
                header_name="Authorization",
                token_prefix="Bearer",
                expires_at=None,
                db=db,
            )
            # 会话关闭后对象会失效，先把断言需要的取值取出来。
            tenant_id = tenant.id
            token_ciphertext = credential.token_ciphertext

        record = self.create_record(
            status=EXECUTION_STATUS_SUCCEEDED,
            http_status_code=200,
            response_body="ok",
        )

        list_response = self.client.get(
            "/api/admin/execution-records",
            headers=self.admin_headers,
        )
        detail_response = self.client.get(
            f"/api/admin/execution-records/{record.id}",
            headers=self.admin_headers,
        )
        credential_response = self.client.get(
            f"/api/admin/tenants/{tenant_id}/callback-credentials",
            headers=self.admin_headers,
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(credential_response.status_code, 200)

        for response in (list_response, detail_response, credential_response):
            raw_body = response.text
            self.assertNotIn(SERVICE_TOKEN, raw_body)
            self.assertNotIn("Bearer ", raw_body)
            self.assertNotIn(token_ciphertext, raw_body)

        # 凭据查询只返回元数据，不返回 Token 明文。
        credentials = credential_response.json()["data"]
        self.assertEqual(len(credentials), 1)
        metadata = credentials[0]
        self.assertEqual(metadata["header_name"], "Authorization")
        self.assertEqual(metadata["token_prefix"], "Bearer")
        self.assertEqual(metadata["status"], "ACTIVE")
        self.assertNotIn("token", metadata)
        self.assertNotIn("token_ciphertext", metadata)


if __name__ == "__main__":
    unittest.main()
