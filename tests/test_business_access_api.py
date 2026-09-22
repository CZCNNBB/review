"""业务接入模块集成测试，需要可用的 PostgreSQL 数据库。

覆盖租户模式下发起审批的完整链路、API Key 认证、流程与业务动作授权、执行参数校验、
幂等与并发、使用记录查询隔离，以及全局模式下不依赖租户表的运行方式。
"""

import os
import threading
import unittest
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.main import create_app
from app.server.integration.src.schemas.business_action_schema import (
    BusinessActionCreateRequest,
)
from app.server.integration.src.service.business_access_service import (
    BusinessAccessService,
)
from app.server.integration.src.service.business_action_service import (
    BusinessActionService,
)
from app.server.organization.src.schemas.organization_schema import PersonCreateRequest
from app.server.organization.src.service.organization_service import OrganizationService
from app.server.process.src.constants import (
    INSTANCE_STATUS_RUNNING,
    NODE_TYPE_APPROVAL,
    NODE_TYPE_END,
    NODE_TYPE_START,
)
from app.server.process.src.schemas.approval_schema import ApprovalStartRequest
from app.server.process.src.schemas.process_schema import (
    ProcessCreateRequest,
    ProcessGraphNodeRequest,
    ProcessGraphSaveRequest,
)
from app.server.process.src.service.process_service import ProcessService
from app.server.tenant.src.models.tenant_model import ProcessUsageRecord
from app.server.tenant.src.repository.tenant_binding_repository import (
    TenantBindingRepository,
)
from app.server.tenant.src.schemas.tenant_schema import (
    TenantCreateRequest,
    TenantUpdateRequest,
)
from app.server.tenant.src.scope.business_access import create_business_access_context
from app.server.tenant.src.service.tenant_binding_service import TenantBindingService
from app.server.tenant.src.service.tenant_service import TenantService
from tests.process_test_helpers import (
    DatabaseTestCaseMixin,
    load_seed_node_definitions,
)


ADMIN_KEY = "test-admin-key"

PAYMENT_ACTION_CODE = "PAYMENT_EXECUTE_BA"
REFUND_ACTION_CODE = "REFUND_EXECUTE_BA"

PAYMENT_SCHEMA = {
    "type": "object",
    "required": ["payment_id", "amount"],
    "properties": {
        "payment_id": {"type": "string", "minLength": 1},
        "amount": {"type": "number", "exclusiveMinimum": 0},
    },
    "additionalProperties": False,
}


def past_datetime() -> datetime:
    """返回一个已经过去的时间，用于构造过期 API Key。"""

    return datetime.now(timezone.utc) - timedelta(days=1)


class BusinessAccessApiTestCase(DatabaseTestCaseMixin, unittest.TestCase):
    """验证租户模式下发起审批的完整链路和权限边界。"""

    def setUp(self) -> None:
        """准备数据库会话、租户、已发布流程和测试客户端。"""

        self.db: Session = self.open_session()
        self.process_service = ProcessService()
        self.tenant_service = TenantService()
        self.binding_service = TenantBindingService()
        self.action_service = BusinessActionService()
        self.seed = load_seed_node_definitions()

        self.previous_tenancy_enabled = os.environ.get("TENANCY_ENABLED")
        self.previous_admin_key = os.environ.get("APPROVAL_ADMIN_KEY")
        os.environ["TENANCY_ENABLED"] = "true"
        os.environ["APPROVAL_ADMIN_KEY"] = ADMIN_KEY

        self.applicant_id = self.create_person("接入发起人")
        self.approver_id = self.create_person("接入审批人")

        self.payment_action_id = self.create_business_action(
            PAYMENT_ACTION_CODE,
            PAYMENT_SCHEMA,
        )
        self.refund_action_id = self.create_business_action(
            REFUND_ACTION_CODE,
            PAYMENT_SCHEMA,
        )

        app = create_app()

        def override_database_session():
            """为接口测试提供真实数据库会话。"""

            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_postgres_engine] = override_database_session
        self.client = TestClient(app)

    def tearDown(self) -> None:
        """关闭客户端、恢复环境变量并清理测试数据。"""

        self.client.close()
        self._restore_environment("TENANCY_ENABLED", self.previous_tenancy_enabled)
        self._restore_environment("APPROVAL_ADMIN_KEY", self.previous_admin_key)
        self.close_session()

    @staticmethod
    def _restore_environment(name: str, previous_value: str | None) -> None:
        """恢复单个环境变量在测试前的值。"""

        if previous_value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous_value

    # ------------------------------------------------------------------
    # 准备数据
    # ------------------------------------------------------------------

    def create_person(self, label: str) -> UUID:
        """创建一名测试人员并登记清理。"""

        person = OrganizationService().create_person(
            PersonCreateRequest(name=f"{label}-{uuid4().hex[:8]}"),
            self.db,
        )
        return self.track_person(person.id)

    def create_tenant(self, label: str) -> tuple[UUID, str]:
        """创建租户和可用的 API Key，返回租户 ID 和密钥明文。"""

        tenant = self.tenant_service.create_tenant(
            TenantCreateRequest(
                code=f"T{uuid4().hex[:8].upper()}",
                name=f"{label}-{uuid4().hex[:8]}",
                callback_base_url=f"https://{uuid4().hex[:8]}.example.com/approval",
            ),
            self.db,
        )
        self.track_tenant(tenant.id)

        api_key = self.tenant_service.create_api_key(
            tenant_id=tenant.id,
            name=f"{label} API Key",
            expires_at=None,
            db=self.db,
        )
        return tenant.id, api_key.api_key

    def create_business_action(self, action_code: str, request_schema: dict) -> UUID:
        """创建业务动作并登记清理。"""

        action = self.action_service.create_action(
            BusinessActionCreateRequest(
                action_code=action_code,
                name=f"业务动作-{action_code}",
                relative_path=f"/business/{action_code.lower()}",
                request_schema_json=request_schema,
            ),
            self.db,
        )
        return self.track_business_action(action.id)

    def publish_linear_process(self, approver_person_ids: list[UUID]) -> UUID:
        """发布 开始 → 人工审批 → 结束 的流程并返回流程 ID。"""

        overview = self.process_service.create_process(
            ProcessCreateRequest(
                name=f"接入流程-{uuid4().hex[:8]}",
                form_schema={"type": "object", "properties": {}},
            ),
            self.db,
        )
        process_id = self.track_process(overview.process.id)
        draft_version = overview.draft_version

        start_node = ProcessGraphNodeRequest(
            id=uuid4(),
            node_definition_id=self.seed[NODE_TYPE_START].id,
            name="开始",
            config={},
            position={"x": 100, "y": 100},
        )
        approval_node = ProcessGraphNodeRequest(
            id=uuid4(),
            node_definition_id=self.seed[NODE_TYPE_APPROVAL].id,
            name="财务审批",
            config={
                "approval_mode": "AND",
                "approvers": [
                    {"person_id": str(person_id)} for person_id in approver_person_ids
                ],
            },
            position={"x": 300, "y": 100},
        )
        end_node = ProcessGraphNodeRequest(
            id=uuid4(),
            node_definition_id=self.seed[NODE_TYPE_END].id,
            name="结束",
            config={"result_status": "APPROVED"},
            position={"x": 500, "y": 100},
        )

        self.process_service.save_graph(
            draft_version.id,
            ProcessGraphSaveRequest(
                revision=draft_version.revision,
                name=draft_version.name,
                form_schema={"type": "object", "properties": {}},
                nodes=[start_node, approval_node, end_node],
                orchestration={
                    "connections": [
                        {
                            "source_node_id": str(start_node.id),
                            "target_node_id": str(approval_node.id),
                        },
                        {
                            "source_node_id": str(approval_node.id),
                            "target_node_id": str(end_node.id),
                        },
                    ]
                },
            ),
            self.db,
        )
        self.process_service.publish_version(draft_version.id, self.db)
        return process_id

    def grant_process(self, tenant_id: UUID, process_id: UUID) -> UUID:
        """授予租户流程使用权并返回授权 ID。"""

        binding = self.binding_service.create_process_binding(
            tenant_id,
            process_id,
            self.db,
        )
        return binding.id

    def grant_action(self, tenant_id: UUID, action_id: UUID) -> UUID:
        """授予租户业务动作使用权并返回授权 ID。"""

        binding = self.binding_service.create_business_action_binding(
            tenant_id,
            action_id,
            self.db,
        )
        return binding.id

    def prepare_tenant(
        self,
        label: str = "接入租户",
        process_id: UUID | None = None,
        grant_process: bool = True,
        grant_action: bool = True,
    ) -> tuple[UUID, str, UUID]:
        """准备一个已授权租户，返回租户 ID、API Key 和流程 ID。"""

        tenant_id, api_key = self.create_tenant(label)
        target_process_id = process_id or self.publish_linear_process([self.approver_id])
        if grant_process:
            self.grant_process(tenant_id, target_process_id)
        if grant_action:
            self.grant_action(tenant_id, self.payment_action_id)
        return tenant_id, api_key, target_process_id

    # ------------------------------------------------------------------
    # 辅助请求
    # ------------------------------------------------------------------

    def build_start_body(
        self,
        business_key: str,
        action_code: str | None = PAYMENT_ACTION_CODE,
        execution_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """构造发起审批请求体。"""

        return {
            "business_key": business_key,
            "title": "供应商付款申请",
            "applicant_person_id": str(self.applicant_id),
            "action_code": action_code,
            "approval_form": {"amount": 10000, "reason": "采购付款"},
            "execution_payload": (
                execution_payload
                if execution_payload is not None
                else {"payment_id": business_key, "amount": 10000}
            ),
        }

    def start_approval(
        self,
        process_id: UUID,
        body: dict[str, Any],
        api_key: str | None = None,
    ):
        """调用发起审批接口并返回原始响应。"""

        headers = {"X-API-Key": api_key} if api_key else {}
        return self.client.post(
            f"/api/processes/{process_id}/instances",
            headers=headers,
            json=body,
        )

    def list_usage_records(
        self,
        tenant_id: UUID,
        **params: Any,
    ):
        """调用租户使用记录列表接口。"""

        return self.client.get(
            f"/api/admin/tenants/{tenant_id}/process-usage-records",
            headers={"X-Admin-Key": ADMIN_KEY},
            params=params,
        )

    def count_usage_records(self, instance_id: UUID) -> int:
        """统计某个审批实例对应的使用记录数量。"""

        record = TenantBindingRepository().get_usage_record_by_instance_id(
            instance_id,
            self.db,
        )
        return 0 if record is None else 1

    # ------------------------------------------------------------------
    # 正常链路
    # ------------------------------------------------------------------

    def test_valid_api_key_starts_approval_and_writes_usage_record(self) -> None:
        """有效 API Key 可以发起审批，并写入一条可查询的租户使用记录。"""

        tenant_id, api_key, process_id = self.prepare_tenant()

        response = self.start_approval(
            process_id,
            self.build_start_body("BIZ-OK-001"),
            api_key,
        )
        self.assertEqual(response.status_code, 201, response.text)
        started = response.json()["data"]
        self.assertEqual(started["status"], INSTANCE_STATUS_RUNNING)
        self.assertEqual(started["current_node_name"], "财务审批")
        self.assertFalse(started["idempotent_replay"])
        self.assertEqual(started["pending_approver_person_ids"], [str(self.approver_id)])

        self.assertEqual(self.count_usage_records(UUID(started["instance_id"])), 1)

        list_response = self.list_usage_records(tenant_id, business_key="BIZ-OK-001")
        self.assertEqual(list_response.status_code, 200, list_response.text)
        records = list_response.json()["data"]
        self.assertEqual(len(records), 1)

        record = records[0]
        self.assertEqual(record["tenant_id"], str(tenant_id))
        self.assertEqual(record["process_id"], str(process_id))
        self.assertEqual(record["approval_instance_id"], started["instance_id"])
        self.assertEqual(record["business_key"], "BIZ-OK-001")
        self.assertEqual(record["action_code"], PAYMENT_ACTION_CODE)
        # 运行状态从 process 运行表读取后组装，不在使用记录中重复保存。
        self.assertEqual(record["approval_status"], INSTANCE_STATUS_RUNNING)
        self.assertEqual(record["current_node_name"], "财务审批")
        self.assertNotIn("execution_payload", record)

        detail_response = self.client.get(
            f"/api/admin/tenants/{tenant_id}/process-usage-records/{record['id']}",
            headers={"X-Admin-Key": ADMIN_KEY},
        )
        self.assertEqual(detail_response.status_code, 200, detail_response.text)
        self.assertEqual(
            detail_response.json()["data"]["approval_instance_id"],
            started["instance_id"],
        )

    def test_start_without_action_code_skips_business_action(self) -> None:
        """action_code 为空时不校验业务动作，也不需要动作授权。"""

        tenant_id, api_key, process_id = self.prepare_tenant(grant_action=False)

        response = self.start_approval(
            process_id,
            self.build_start_body(
                "BIZ-NO-ACTION-001",
                action_code=None,
                execution_payload={},
            ),
            api_key,
        )
        self.assertEqual(response.status_code, 201, response.text)

        records = self.list_usage_records(tenant_id).json()["data"]
        self.assertIsNone(records[0]["action_code"])

    # ------------------------------------------------------------------
    # API Key 认证
    # ------------------------------------------------------------------

    def test_missing_api_key_returns_401(self) -> None:
        """缺少 X-API-Key 时返回 401，不自动降级为全局模式。"""

        _, _, process_id = self.prepare_tenant()

        response = self.start_approval(
            process_id,
            self.build_start_body("BIZ-NO-KEY"),
        )
        self.assertEqual(response.status_code, 401, response.text)

    def test_invalid_api_key_returns_401(self) -> None:
        """无效 API Key 返回 401。"""

        _, _, process_id = self.prepare_tenant()

        response = self.start_approval(
            process_id,
            self.build_start_body("BIZ-BAD-KEY"),
            "appr_live_not_exists.deadbeef",
        )
        self.assertEqual(response.status_code, 401, response.text)

    def test_expired_api_key_returns_401(self) -> None:
        """已经过期的 API Key 返回 401。"""

        tenant_id, _ = self.create_tenant("过期租户")
        process_id = self.publish_linear_process([self.approver_id])
        self.grant_process(tenant_id, process_id)
        self.grant_action(tenant_id, self.payment_action_id)

        expired_key = self.tenant_service.create_api_key(
            tenant_id=tenant_id,
            name="过期密钥",
            expires_at=None,
            db=self.db,
        )
        # 直接写入过期时间，模拟密钥在有效期内被使用后又自然过期。
        expired_key.expires_at = past_datetime()
        self.db.add(expired_key)
        self.db.commit()

        response = self.start_approval(
            process_id,
            self.build_start_body("BIZ-EXPIRED"),
            expired_key.api_key,
        )
        self.assertEqual(response.status_code, 401, response.text)

    def test_revoked_api_key_returns_401(self) -> None:
        """已经撤销的 API Key 返回 401。"""

        tenant_id, api_key = self.create_tenant("撤销租户")
        process_id = self.publish_linear_process([self.approver_id])
        self.grant_process(tenant_id, process_id)
        self.grant_action(tenant_id, self.payment_action_id)

        api_key_record = TenantService().list_api_keys(tenant_id, self.db)[0]
        self.tenant_service.revoke_api_key(tenant_id, api_key_record.id, self.db)

        response = self.start_approval(
            process_id,
            self.build_start_body("BIZ-REVOKED"),
            api_key,
        )
        self.assertEqual(response.status_code, 401, response.text)

    def test_disabled_tenant_returns_401(self) -> None:
        """租户停用后其 API Key 不能再发起审批。"""

        tenant_id, api_key, process_id = self.prepare_tenant()

        self.tenant_service.update_tenant(
            tenant_id,
            TenantUpdateRequest(status="DISABLED"),
            self.db,
        )

        response = self.start_approval(
            process_id,
            self.build_start_body("BIZ-DISABLED-TENANT"),
            api_key,
        )
        self.assertEqual(response.status_code, 401, response.text)

    # ------------------------------------------------------------------
    # 流程授权
    # ------------------------------------------------------------------

    def test_process_without_binding_returns_403(self) -> None:
        """租户没有绑定审批流时返回 403。"""

        tenant_id, api_key = self.create_tenant("未授权流程租户")
        self.grant_action(tenant_id, self.payment_action_id)
        unbound_process_id = self.publish_linear_process([self.approver_id])

        response = self.start_approval(
            unbound_process_id,
            self.build_start_body("BIZ-UNBOUND-PROCESS"),
            api_key,
        )
        self.assertEqual(response.status_code, 403, response.text)

    def test_disabled_process_binding_returns_403(self) -> None:
        """流程授权停用后不能新发起审批。"""

        tenant_id, api_key, process_id = self.prepare_tenant()
        binding_id = self.binding_service.list_process_bindings(tenant_id, self.db)[0].id

        self.binding_service.update_process_binding_status(
            tenant_id,
            binding_id,
            "DISABLED",
            self.db,
        )

        response = self.start_approval(
            process_id,
            self.build_start_body("BIZ-DISABLED-PROCESS"),
            api_key,
        )
        self.assertEqual(response.status_code, 403, response.text)

    def test_disabled_process_binding_does_not_block_running_instance(self) -> None:
        """流程授权停用只影响新请求，已经运行的审批实例继续存在。"""

        tenant_id, api_key, process_id = self.prepare_tenant()
        started = self.start_approval(
            process_id,
            self.build_start_body("BIZ-RUNNING-001"),
            api_key,
        ).json()["data"]

        binding_id = self.binding_service.list_process_bindings(tenant_id, self.db)[0].id
        self.binding_service.update_process_binding_status(
            tenant_id,
            binding_id,
            "DISABLED",
            self.db,
        )

        detail_response = self.client.get(
            f"/api/approval-instances/{started['instance_id']}",
            headers={"X-API-Key": api_key},
        )
        self.assertEqual(detail_response.status_code, 200, detail_response.text)
        self.assertEqual(
            detail_response.json()["data"]["status"],
            INSTANCE_STATUS_RUNNING,
        )

    def test_instance_detail_and_timeline_are_isolated_by_tenant(self) -> None:
        """审批详情和时间线只能由实例所属租户查询。"""

        _, owner_api_key, process_id = self.prepare_tenant("实例所属租户")
        _, other_api_key = self.create_tenant("其他租户")
        started = self.start_approval(
            process_id,
            self.build_start_body("BIZ-INSTANCE-SCOPE"),
            owner_api_key,
        ).json()["data"]
        instance_id = started["instance_id"]

        protected_paths = [
            f"/api/approval-instances/{instance_id}",
            f"/api/approval-instances/{instance_id}/timeline",
        ]
        for path in protected_paths:
            with self.subTest(path=path, access="missing_api_key"):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401, response.text)

            with self.subTest(path=path, access="other_tenant"):
                response = self.client.get(
                    path,
                    headers={"X-API-Key": other_api_key},
                )
                self.assertEqual(response.status_code, 403, response.text)

            with self.subTest(path=path, access="owner_tenant"):
                response = self.client.get(
                    path,
                    headers={"X-API-Key": owner_api_key},
                )
                self.assertEqual(response.status_code, 200, response.text)

    def test_tenant_cannot_use_another_tenants_process(self) -> None:
        """租户之间不共享流程授权。"""

        first_tenant, _, process_id = self.prepare_tenant("甲租户")
        second_tenant, second_key = self.create_tenant("乙租户")
        self.grant_action(second_tenant, self.payment_action_id)

        response = self.start_approval(
            process_id,
            self.build_start_body("BIZ-CROSS-PROCESS"),
            second_key,
        )
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.list_usage_records(first_tenant).json()["data"], [])

    # ------------------------------------------------------------------
    # 业务动作授权与参数校验
    # ------------------------------------------------------------------

    def test_unknown_business_action_returns_404(self) -> None:
        """业务动作不存在时返回 404。"""

        _, api_key, process_id = self.prepare_tenant()

        response = self.start_approval(
            process_id,
            self.build_start_body("BIZ-UNKNOWN-ACTION", action_code="NOT_EXISTS_ACTION"),
            api_key,
        )
        self.assertEqual(response.status_code, 404, response.text)

    def test_disabled_business_action_returns_409(self) -> None:
        """业务动作停用后不能再用于新申请。"""

        _, api_key, process_id = self.prepare_tenant()

        update_response = self.client.patch(
            f"/api/admin/business-actions/{self.payment_action_id}",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={"status": "DISABLED"},
        )
        self.assertEqual(update_response.status_code, 200, update_response.text)

        response = self.start_approval(
            process_id,
            self.build_start_body("BIZ-DISABLED-ACTION"),
            api_key,
        )
        self.assertEqual(response.status_code, 409, response.text)

    def test_action_without_tenant_binding_returns_403(self) -> None:
        """租户没有绑定业务动作时返回 403，不暴露其他租户的绑定情况。"""

        tenant_id, api_key, process_id = self.prepare_tenant(grant_action=False)

        response = self.start_approval(
            process_id,
            self.build_start_body("BIZ-UNBOUND-ACTION"),
            api_key,
        )
        self.assertEqual(response.status_code, 403, response.text)

        binding_id = self.grant_action(tenant_id, self.payment_action_id)
        self.binding_service.update_business_action_binding_status(
            tenant_id,
            binding_id,
            "DISABLED",
            self.db,
        )

        disabled_response = self.start_approval(
            process_id,
            self.build_start_body("BIZ-DISABLED-ACTION-BINDING"),
            api_key,
        )
        self.assertEqual(disabled_response.status_code, 403, disabled_response.text)

    def test_execution_payload_validation_returns_422_with_field_path(self) -> None:
        """执行参数不符合业务动作规则时返回 422 和具体字段路径。"""

        _, api_key, process_id = self.prepare_tenant()

        response = self.start_approval(
            process_id,
            self.build_start_body(
                "BIZ-BAD-PAYLOAD",
                execution_payload={"amount": -1},
            ),
            api_key,
        )
        self.assertEqual(response.status_code, 422, response.text)

        detail = response.json()["detail"]
        self.assertEqual(detail["message"], "业务执行参数校验未通过")
        fields = [issue["field"] for issue in detail["issues"]]
        self.assertIn("execution_payload", fields)
        self.assertTrue(
            any("payment_id" in issue["message"] for issue in detail["issues"])
        )

    def test_invalid_execution_payload_does_not_create_instance(self) -> None:
        """参数校验失败时不产生审批实例和使用记录。"""

        tenant_id, api_key, process_id = self.prepare_tenant()

        response = self.start_approval(
            process_id,
            self.build_start_body(
                "BIZ-BAD-PAYLOAD-2",
                execution_payload={"payment_id": "", "amount": 0},
            ),
            api_key,
        )
        self.assertEqual(response.status_code, 422, response.text)

        records = self.list_usage_records(tenant_id).json()["data"]
        self.assertEqual(records, [])

    # ------------------------------------------------------------------
    # 幂等与并发
    # ------------------------------------------------------------------

    def test_repeat_request_returns_same_instance(self) -> None:
        """相同请求重复发起时返回原审批实例，并且只写入一条使用记录。"""

        tenant_id, api_key, process_id = self.prepare_tenant()
        body = self.build_start_body("BIZ-IDEMPOTENT-001")

        first = self.start_approval(process_id, body, api_key)
        self.assertEqual(first.status_code, 201, first.text)
        first_data = first.json()["data"]
        self.assertFalse(first_data["idempotent_replay"])

        second = self.start_approval(process_id, body, api_key)
        self.assertEqual(second.status_code, 201, second.text)
        second_data = second.json()["data"]
        self.assertTrue(second_data["idempotent_replay"])
        self.assertEqual(second_data["instance_id"], first_data["instance_id"])

        self.assertEqual(
            self.count_usage_records(UUID(first_data["instance_id"])),
            1,
        )
        records = self.list_usage_records(
            tenant_id,
            business_key="BIZ-IDEMPOTENT-001",
        ).json()["data"]
        self.assertEqual(len(records), 1)

    def test_same_business_key_with_changed_content_returns_409(self) -> None:
        """同一业务单号但内容变化时返回 409，不静默复用旧实例。"""

        _, api_key, process_id = self.prepare_tenant()

        first = self.start_approval(
            process_id,
            self.build_start_body("BIZ-CHANGED-001"),
            api_key,
        )
        self.assertEqual(first.status_code, 201, first.text)

        changed_body = self.build_start_body(
            "BIZ-CHANGED-001",
            execution_payload={"payment_id": "BIZ-CHANGED-001", "amount": 99999},
        )
        changed = self.start_approval(process_id, changed_body, api_key)
        self.assertEqual(changed.status_code, 409, changed.text)

    def test_concurrent_start_creates_single_instance_and_record(self) -> None:
        """并发发起相同业务单据时只产生一个审批实例和一条使用记录。"""

        tenant_id, api_key, process_id = self.prepare_tenant()
        business_key = "BIZ-CONCURRENT-001"
        request = ApprovalStartRequest(**self.build_start_body(business_key))
        context = create_business_access_context(tenant_id)

        results: list[tuple[UUID, bool]] = []
        errors: list = []
        barrier = threading.Barrier(2, timeout=10)

        def worker() -> None:
            """在独立会话中发起一次审批。

            会话关闭后 ORM 对象会失效，因此在会话内就把需要断言的结果取成普通值。
            """

            try:
                with Session(self.engine) as session:
                    barrier.wait()
                    started = BusinessAccessService().start_approval(
                        process_id,
                        request,
                        context,
                        session,
                    )
                    results.append(
                        (started.instance.id, started.idempotent_replay)
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)

        instance_ids = {instance_id for instance_id, _ in results}
        self.assertEqual(len(instance_ids), 1)
        # 两个请求只有一个真正创建了实例，另一个返回幂等重放结果。
        self.assertEqual(
            sorted(idempotent_replay for _, idempotent_replay in results),
            [False, True],
        )
        self.assertEqual(self.count_usage_records(instance_ids.pop()), 1)

        records = self.list_usage_records(
            tenant_id,
            business_key=business_key,
        ).json()["data"]
        self.assertEqual(len(records), 1)

    def test_usage_record_conflict_rolls_back_instance(self) -> None:
        """使用记录写入失败时审批实例整体回滚，不产生孤立数据。"""

        tenant_id, api_key, process_id = self.prepare_tenant()
        business_key = "BIZ-ORPHAN-001"

        # 预先占用同一租户下的同一业务单据标识，让使用记录的唯一约束在提交时失败。
        TenantBindingRepository().add_usage_record(
            ProcessUsageRecord(
                tenant_id=tenant_id,
                process_id=process_id,
                process_version_id=uuid4(),
                approval_instance_id=uuid4(),
                business_key=business_key,
            ),
            self.db,
        )
        self.db.commit()

        response = self.start_approval(
            process_id,
            self.build_start_body(business_key),
            api_key,
        )
        self.assertEqual(response.status_code, 409, response.text)

        # 审批实例和首批任务必须在同一个事务中回滚干净。
        from sqlalchemy import text

        instance_count = self.db.execute(
            text(
                "SELECT count(*) FROM process.approval_instance "
                "WHERE business_key = :business_key"
            ),
            {"business_key": business_key},
        ).scalar()
        self.assertEqual(instance_count, 0)

    def test_same_business_key_in_different_tenants_is_allowed(self) -> None:
        """幂等范围包含租户，不同租户可以使用相同业务单号。"""

        process_id = self.publish_linear_process([self.approver_id])
        _, first_key, _ = self.prepare_tenant(
            "甲租户",
            process_id=process_id,
        )
        second_tenant_id, second_key, _ = self.prepare_tenant(
            "乙租户",
            process_id=process_id,
        )

        body = self.build_start_body("BIZ-SHARED-001")
        first = self.start_approval(process_id, body, first_key)
        second = self.start_approval(process_id, body, second_key)

        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertNotEqual(
            first.json()["data"]["instance_id"],
            second.json()["data"]["instance_id"],
        )
        self.assertFalse(second.json()["data"]["idempotent_replay"])
        self.assertEqual(
            len(self.list_usage_records(second_tenant_id).json()["data"]),
            1,
        )

    # ------------------------------------------------------------------
    # 使用记录租户隔离
    # ------------------------------------------------------------------

    def test_usage_record_query_does_not_leak_other_tenants(self) -> None:
        """使用记录查询和详情都不会返回其他租户的数据。"""

        process_id = self.publish_linear_process([self.approver_id])
        first_tenant_id, first_key, _ = self.prepare_tenant("甲租户", process_id)
        second_tenant_id, second_key, _ = self.prepare_tenant("乙租户", process_id)

        self.start_approval(
            process_id,
            self.build_start_body("BIZ-FIRST-001"),
            first_key,
        )
        self.start_approval(
            process_id,
            self.build_start_body("BIZ-SECOND-001"),
            second_key,
        )

        first_records = self.list_usage_records(first_tenant_id).json()["data"]
        self.assertEqual(
            [record["business_key"] for record in first_records],
            ["BIZ-FIRST-001"],
        )

        # 通过甲租户的路径访问乙租户的使用记录按不存在处理。
        second_record_id = self.list_usage_records(second_tenant_id).json()["data"][0][
            "id"
        ]
        cross_response = self.client.get(
            f"/api/admin/tenants/{first_tenant_id}/process-usage-records/"
            f"{second_record_id}",
            headers={"X-Admin-Key": ADMIN_KEY},
        )
        self.assertEqual(cross_response.status_code, 404, cross_response.text)

    def test_usage_record_list_supports_filters(self) -> None:
        """使用记录列表支持按业务单号、动作和流程筛选。"""

        tenant_id, api_key, process_id = self.prepare_tenant()
        self.grant_action(tenant_id, self.refund_action_id)

        self.start_approval(
            process_id,
            self.build_start_body("BIZ-FILTER-A"),
            api_key,
        )
        self.start_approval(
            process_id,
            self.build_start_body(
                "BIZ-FILTER-B",
                action_code=REFUND_ACTION_CODE,
            ),
            api_key,
        )

        self.assertEqual(
            len(self.list_usage_records(tenant_id, business_key="BIZ-FILTER-A").json()[
                "data"
            ]),
            1,
        )
        self.assertEqual(
            len(self.list_usage_records(tenant_id, action_code=PAYMENT_ACTION_CODE).json()[
                "data"
            ]),
            1,
        )
        self.assertEqual(
            len(self.list_usage_records(tenant_id, process_id=str(process_id)).json()[
                "data"
            ]),
            2,
        )

    # ------------------------------------------------------------------
    # 全局模式
    # ------------------------------------------------------------------

    def test_global_mode_starts_without_api_key_or_tenant_tables(self) -> None:
        """关闭租户能力后不要求 API Key，也不创建租户使用记录。"""

        os.environ["TENANCY_ENABLED"] = "false"
        process_id = self.publish_linear_process([self.approver_id])

        response = self.start_approval(
            process_id,
            self.build_start_body("BIZ-GLOBAL-001"),
        )
        self.assertEqual(response.status_code, 201, response.text)
        started = response.json()["data"]

        # 全局模式下不写入任何租户使用记录。
        self.assertEqual(self.count_usage_records(UUID(started["instance_id"])), 0)

    def test_global_mode_does_not_require_process_binding(self) -> None:
        """关闭租户能力后不校验流程授权和动作授权，也不需要绑定记录。"""

        os.environ["TENANCY_ENABLED"] = "false"
        tenant_id, _, process_id = self.prepare_tenant(
            grant_process=False,
            grant_action=False,
        )

        response = self.start_approval(
            process_id,
            self.build_start_body("BIZ-GLOBAL-NO-BINDING"),
        )
        self.assertEqual(response.status_code, 201, response.text)

        # 全局模式不读写租户绑定表，因此不会产生使用记录。
        self.assertEqual(
            TenantBindingRepository().list_usage_records(tenant_id, self.db),
            [],
        )

    # ------------------------------------------------------------------
    # 管理接口
    # ------------------------------------------------------------------

    def test_process_binding_creation_requires_existing_process(self) -> None:
        """创建流程授权前必须确认流程存在。"""

        tenant_id, _ = self.create_tenant("授权租户")

        response = self.client.post(
            f"/api/admin/tenants/{tenant_id}/process-bindings",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={"process_id": str(uuid4())},
        )
        self.assertEqual(response.status_code, 404, response.text)

    def test_process_binding_creation_is_idempotent_and_reenables(self) -> None:
        """重复授权返回同一条记录，已经停用的授权会被重新启用。"""

        tenant_id, _ = self.create_tenant("授权租户")
        process_id = self.publish_linear_process([self.approver_id])

        first = self.client.post(
            f"/api/admin/tenants/{tenant_id}/process-bindings",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={"process_id": str(process_id)},
        )
        self.assertEqual(first.status_code, 201, first.text)

        binding_id = first.json()["data"]["id"]
        disabled = self.client.patch(
            f"/api/admin/tenants/{tenant_id}/process-bindings/{binding_id}",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={"status": "DISABLED"},
        )
        self.assertEqual(disabled.status_code, 200, disabled.text)
        self.assertEqual(disabled.json()["data"]["status"], "DISABLED")

        again = self.client.post(
            f"/api/admin/tenants/{tenant_id}/process-bindings",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={"process_id": str(process_id)},
        )
        self.assertEqual(again.status_code, 201, again.text)
        self.assertEqual(again.json()["data"]["id"], binding_id)
        self.assertEqual(again.json()["data"]["status"], "ENABLED")

    def test_process_binding_patch_rejects_other_tenant(self) -> None:
        """不能用其他租户的路径修改授权记录。"""

        first_tenant, _, process_id = self.prepare_tenant("甲租户")
        second_tenant, _ = self.create_tenant("乙租户")
        binding_id = self.binding_service.list_process_bindings(
            first_tenant,
            self.db,
        )[0].id

        response = self.client.patch(
            f"/api/admin/tenants/{second_tenant}/process-bindings/{binding_id}",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={"status": "DISABLED"},
        )
        self.assertEqual(response.status_code, 404, response.text)

    def test_business_action_management_requires_existing_action(self) -> None:
        """业务动作授权只能绑定已经存在的动作。"""

        tenant_id, _ = self.create_tenant("授权租户")

        response = self.client.post(
            f"/api/admin/tenants/{tenant_id}/business-action-bindings",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={"business_action_id": str(uuid4())},
        )
        self.assertEqual(response.status_code, 404, response.text)

    def test_business_action_binding_creation_is_idempotent_and_reenables(self) -> None:
        """业务动作授权同样支持重复授权和停用后重新启用。"""

        tenant_id, _ = self.create_tenant("授权租户")

        first = self.client.post(
            f"/api/admin/tenants/{tenant_id}/business-action-bindings",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={"business_action_id": str(self.payment_action_id)},
        )
        self.assertEqual(first.status_code, 201, first.text)
        binding_id = first.json()["data"]["id"]

        disabled = self.client.patch(
            f"/api/admin/tenants/{tenant_id}/business-action-bindings/{binding_id}",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={"status": "DISABLED"},
        )
        self.assertEqual(disabled.status_code, 200, disabled.text)
        self.assertEqual(disabled.json()["data"]["status"], "DISABLED")

        again = self.client.post(
            f"/api/admin/tenants/{tenant_id}/business-action-bindings",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={"business_action_id": str(self.payment_action_id)},
        )
        self.assertEqual(again.status_code, 201, again.text)
        self.assertEqual(again.json()["data"]["id"], binding_id)
        self.assertEqual(again.json()["data"]["status"], "ENABLED")

    def test_binding_list_endpoints_return_all_records(self) -> None:
        """授权列表包含已经停用的记录，便于后台核对历史授权。"""

        tenant_id, _, process_id = self.prepare_tenant()

        process_bindings = self.client.get(
            f"/api/admin/tenants/{tenant_id}/process-bindings",
            headers={"X-Admin-Key": ADMIN_KEY},
        )
        self.assertEqual(process_bindings.status_code, 200, process_bindings.text)
        self.assertEqual(
            [item["process_id"] for item in process_bindings.json()["data"]],
            [str(process_id)],
        )

        action_bindings = self.client.get(
            f"/api/admin/tenants/{tenant_id}/business-action-bindings",
            headers={"X-Admin-Key": ADMIN_KEY},
        )
        self.assertEqual(action_bindings.status_code, 200, action_bindings.text)
        self.assertEqual(
            [item["business_action_id"] for item in action_bindings.json()["data"]],
            [str(self.payment_action_id)],
        )

    def test_business_action_admin_endpoints(self) -> None:
        """业务动作可以创建、查询列表和读取详情。"""

        create_response = self.client.post(
            "/api/admin/business-actions",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={
                "action_code": f"ACTION_{uuid4().hex[:8].upper()}",
                "name": "接口创建的动作",
                "http_method": "put",
                "relative_path": "/business/interface-action",
                "request_schema_json": {"type": "object"},
                "timeout_ms": 3000,
            },
        )
        self.assertEqual(create_response.status_code, 201, create_response.text)
        created = create_response.json()["data"]
        self.track_business_action(UUID(created["id"]))
        self.assertEqual(created["http_method"], "PUT")
        self.assertEqual(created["success_status_codes"], [])
        self.assertEqual(created["timeout_ms"], 3000)

        list_response = self.client.get(
            "/api/admin/business-actions",
            headers={"X-Admin-Key": ADMIN_KEY},
            params={"limit": 200},
        )
        self.assertEqual(list_response.status_code, 200, list_response.text)
        self.assertIn(
            created["id"],
            [action["id"] for action in list_response.json()["data"]],
        )

        detail_response = self.client.get(
            f"/api/admin/business-actions/{created['id']}",
            headers={"X-Admin-Key": ADMIN_KEY},
        )
        self.assertEqual(detail_response.status_code, 200, detail_response.text)
        self.assertEqual(detail_response.json()["data"]["name"], "接口创建的动作")

    def test_business_action_rejects_non_object_request_schema(self) -> None:
        """业务动作的请求参数 Schema 根类型必须是 object。"""

        response = self.client.post(
            "/api/admin/business-actions",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={
                "action_code": f"ACTION_{uuid4().hex[:8].upper()}",
                "name": "非法 Schema 动作",
                "relative_path": "/business/invalid",
                "request_schema_json": {"type": "array"},
            },
        )
        self.assertEqual(response.status_code, 422, response.text)

    def test_business_action_rejects_full_url_relative_path(self) -> None:
        """相对路径不能是完整 URL。"""

        response = self.client.post(
            "/api/admin/business-actions",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={
                "action_code": f"ACTION_{uuid4().hex[:8].upper()}",
                "name": "完整地址动作",
                "relative_path": "https://evil.example.com/pay",
            },
        )
        self.assertEqual(response.status_code, 422, response.text)


if __name__ == "__main__":
    unittest.main()
