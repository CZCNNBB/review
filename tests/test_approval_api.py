"""审批运行接口集成测试，需要可用的 PostgreSQL 数据库。

覆盖发起审批、审批详情、运行时间线、待办查询、同意和拒绝六个接口，以及 403、
404、409 和 422 四类错误响应。流程定义通过 Service 准备，接口测试只关注运行层。
"""

import time
import unittest
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.main import create_app
from app.server.organization.src.schemas.organization_schema import PersonCreateRequest
from app.server.organization.src.service.organization_service import OrganizationService
from app.server.process.src.constants import (
    INSTANCE_STATUS_APPROVED,
    INSTANCE_STATUS_REJECTED,
    INSTANCE_STATUS_RUNNING,
    NODE_TYPE_APPROVAL,
    NODE_TYPE_END,
    NODE_TYPE_START,
    TASK_STATUS_CANCELLED,
    TASK_STATUS_PENDING,
)
from app.server.process.src.schemas.process_schema import (
    ProcessCreateRequest,
    ProcessGraphNodeRequest,
    ProcessGraphSaveRequest,
)
from app.server.process.src.service.process_service import ProcessService
from tests.process_test_helpers import (
    DatabaseTestCaseMixin,
    load_seed_node_definitions,
)


class ApprovalApiTestCase(DatabaseTestCaseMixin, unittest.TestCase):
    """验证审批运行接口的完整链路和错误响应。"""

    def setUp(self) -> None:
        """准备数据库会话、已发布流程和测试客户端。"""

        self.db: Session = self.open_session()
        self.process_service = ProcessService()
        self.seed = load_seed_node_definitions()

        self.applicant_id = self.create_person("接口发起人")
        self.approver_a = self.create_person("接口审批人A")
        self.approver_b = self.create_person("接口审批人B")

        app = create_app()

        def override_database_session():
            """为接口测试提供真实数据库会话。"""

            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_postgres_engine] = override_database_session
        self.client = TestClient(app)

    def tearDown(self) -> None:
        """关闭客户端并清理测试数据。"""

        self.client.close()
        self.close_session()

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def create_person(self, label: str) -> UUID:
        """创建一名测试人员并登记清理。"""

        person = OrganizationService().create_person(
            PersonCreateRequest(name=f"{label}-{uuid4().hex[:8]}"),
            self.db,
        )
        return self.track_person(person.id)

    def publish_linear_process(
        self,
        approver_person_ids: list[UUID],
        approval_mode: str = "AND",
        form_schema: dict[str, Any] | None = None,
    ) -> UUID:
        """发布 开始 → 人工审批 → 结束 的流程并返回流程 ID。"""

        overview = self.process_service.create_process(
            ProcessCreateRequest(
                name=f"接口运行流程-{uuid4().hex[:8]}",
                form_schema=form_schema or {"type": "object", "properties": {}},
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
                "approval_mode": approval_mode,
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
                form_schema=form_schema or {"type": "object", "properties": {}},
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

    def start_instance(
        self,
        process_id: UUID,
        business_key: str | None = None,
        approval_form: dict[str, Any] | None = None,
    ) -> dict:
        """通过接口发起审批并返回响应数据。"""

        response = self.client.post(
            f"/api/processes/{process_id}/instances",
            json={
                "business_key": business_key or f"BIZ-{uuid4().hex[:8]}",
                "title": "供应商付款申请",
                "applicant_person_id": str(self.applicant_id),
                "action_code": "PAYMENT_EXECUTE",
                "approval_form": approval_form or {},
                "execution_payload": {"payment_id": "PAY-001"},
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["data"]

    def list_tasks(self, person_id: UUID, status: str = TASK_STATUS_PENDING) -> list[dict]:
        """通过接口查询人员任务。"""

        response = self.client.get(
            "/api/approval-tasks",
            params={"person_id": str(person_id), "status": status},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    def handle_task(self, task_id: str, person_id: UUID, action: str, comment=None):
        """通过接口同意或拒绝任务并返回原始响应。"""

        return self.client.post(
            f"/api/approval-tasks/{task_id}/{action}",
            json={"person_id": str(person_id), "comment": comment},
        )

    # ------------------------------------------------------------------
    # 发起审批与详情
    # ------------------------------------------------------------------

    def test_start_instance_and_read_detail_and_timeline(self) -> None:
        """发起审批后可以读取详情和运行时间线。"""

        process_id = self.publish_linear_process([self.approver_a, self.approver_b])
        started = self.start_instance(process_id, business_key="BIZ-API-001")

        self.assertEqual(started["status"], INSTANCE_STATUS_RUNNING)
        self.assertEqual(started["current_node_name"], "财务审批")
        self.assertEqual(started["process_version_no"], 1)
        self.assertFalse(started["idempotent_replay"])
        self.assertEqual(
            set(started["pending_approver_person_ids"]),
            {str(self.approver_a), str(self.approver_b)},
        )

        detail_response = self.client.get(
            f"/api/approval-instances/{started['instance_id']}"
        )
        self.assertEqual(detail_response.status_code, 200, detail_response.text)
        detail = detail_response.json()["data"]
        self.assertEqual(detail["business_key"], "BIZ-API-001")
        self.assertEqual(detail["title"], "供应商付款申请")
        self.assertEqual(detail["action_code"], "PAYMENT_EXECUTE")
        self.assertEqual(detail["current_node"]["node_name"], "财务审批")
        self.assertEqual(
            [execution["node_type"] for execution in detail["node_executions"]],
            [NODE_TYPE_START, NODE_TYPE_APPROVAL],
        )
        self.assertEqual(len(detail["pending_tasks"]), 2)
        self.assertIsNone(detail["finished_at"])
        self.assertIsNotNone(detail["duration_ms"])
        # 审批单数据用于展示，业务执行参数不通过详情接口返回。
        self.assertNotIn("execution_payload", detail)

        timeline_response = self.client.get(
            f"/api/approval-instances/{started['instance_id']}/timeline"
        )
        self.assertEqual(timeline_response.status_code, 200, timeline_response.text)
        timeline = timeline_response.json()["data"]
        self.assertEqual(len(timeline["entries"]), 2)

        start_entry = timeline["entries"][0]
        self.assertEqual(start_entry["node_execution"]["node_type"], NODE_TYPE_START)
        self.assertEqual(len(start_entry["tasks"]), 0)
        approval_entry = timeline["entries"][1]
        self.assertEqual(len(approval_entry["tasks"]), 2)
        self.assertEqual(
            approval_entry["tasks"][0]["node_name"],
            "财务审批",
        )
        self.assertEqual(
            approval_entry["tasks"][0]["instance_title"],
            "供应商付款申请",
        )

    def test_duplicate_start_returns_same_instance(self) -> None:
        """相同幂等键重复发起返回原审批实例。"""

        process_id = self.publish_linear_process([self.approver_a])
        business_key = f"BIZ-{uuid4().hex[:8]}"
        first = self.start_instance(process_id, business_key=business_key)
        second = self.start_instance(process_id, business_key=business_key)

        self.assertEqual(first["instance_id"], second["instance_id"])
        self.assertTrue(second["idempotent_replay"])

    def test_changed_content_returns_409(self) -> None:
        """同一业务单号提交不同内容时返回 409，而不是原审批实例。"""

        process_id = self.publish_linear_process([self.approver_a])
        business_key = f"BIZ-{uuid4().hex[:8]}"
        self.start_instance(
            process_id,
            business_key=business_key,
            approval_form={"amount": 100},
        )

        response = self.client.post(
            f"/api/processes/{process_id}/instances",
            json={
                "business_key": business_key,
                "title": "供应商付款申请",
                "applicant_person_id": str(self.applicant_id),
                "action_code": "PAYMENT_EXECUTE",
                "approval_form": {"amount": 999},
                "execution_payload": {"payment_id": "PAY-001"},
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("不一致", response.json()["detail"])

    def test_cancelled_task_duration_stops_growing(self) -> None:
        """被取消任务的耗时停在取消时刻，不再随时间增长。"""

        process_id = self.publish_linear_process([self.approver_a, self.approver_b])
        self.start_instance(process_id)
        task = self.list_tasks(self.approver_a)[0]
        self.handle_task(task["id"], self.approver_a, "reject")

        cancelled_task = self.list_tasks(self.approver_b, status=TASK_STATUS_CANCELLED)[0]
        self.assertIsNotNone(cancelled_task["cancelled_at"])
        self.assertIsNone(cancelled_task["handled_at"])
        self.assertIsNotNone(cancelled_task["duration_ms"])

        time.sleep(0.05)
        cancelled_again = self.list_tasks(self.approver_b, status=TASK_STATUS_CANCELLED)[0]
        self.assertEqual(cancelled_task["duration_ms"], cancelled_again["duration_ms"])

    def test_invalid_approval_form_returns_422(self) -> None:
        """审批单数据不符合表单 Schema 时返回结构化校验问题。"""

        form_schema = {
            "type": "object",
            "required": ["amount"],
            "properties": {"amount": {"type": "number"}},
        }
        process_id = self.publish_linear_process(
            [self.approver_a],
            form_schema=form_schema,
        )
        response = self.client.post(
            f"/api/processes/{process_id}/instances",
            json={
                "business_key": f"BIZ-{uuid4().hex[:8]}",
                "title": "供应商付款申请",
                "approval_form": {},
            },
        )

        self.assertEqual(response.status_code, 422)
        issues = response.json()["detail"]["issues"]
        self.assertTrue(issues)
        # 缺少必填项时问题定位在审批单对象上，提示文本会指出具体字段。
        self.assertEqual(issues[0]["field"], "approval_form")
        self.assertEqual(issues[0]["code"], "APPROVAL_FORM_INVALID")
        self.assertIn("amount", issues[0]["message"])

    def test_missing_instance_returns_404(self) -> None:
        """查询不存在的审批实例返回 404。"""

        response = self.client.get(f"/api/approval-instances/{uuid4()}")
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------
    # 审批操作
    # ------------------------------------------------------------------

    def test_and_mode_approval_flow_through_api(self) -> None:
        """AND 模式下全部审批人同意后实例通过。"""

        process_id = self.publish_linear_process([self.approver_a, self.approver_b])
        started = self.start_instance(process_id)
        instance_id = started["instance_id"]

        first_tasks = self.list_tasks(self.approver_a)
        self.assertEqual(len(first_tasks), 1)
        self.assertEqual(first_tasks[0]["instance_id"], instance_id)
        self.assertEqual(first_tasks[0]["status"], TASK_STATUS_PENDING)

        first_response = self.handle_task(
            first_tasks[0]["id"],
            self.approver_a,
            "approve",
            comment="同意付款",
        )
        self.assertEqual(first_response.status_code, 200, first_response.text)
        first_result = first_response.json()["data"]
        self.assertEqual(first_result["instance_status"], INSTANCE_STATUS_RUNNING)
        self.assertFalse(first_result["idempotent_replay"])

        second_tasks = self.list_tasks(self.approver_b)
        second_response = self.handle_task(second_tasks[0]["id"], self.approver_b, "approve")
        self.assertEqual(second_response.status_code, 200, second_response.text)
        self.assertEqual(
            second_response.json()["data"]["instance_status"],
            INSTANCE_STATUS_APPROVED,
        )
        self.assertIsNone(second_response.json()["data"]["current_node_name"])

        detail = self.client.get(f"/api/approval-instances/{instance_id}").json()["data"]
        self.assertEqual(detail["status"], INSTANCE_STATUS_APPROVED)
        self.assertIsNone(detail["current_node"])
        self.assertEqual(
            [execution["node_type"] for execution in detail["node_executions"]],
            [NODE_TYPE_START, NODE_TYPE_APPROVAL, NODE_TYPE_END],
        )
        self.assertEqual(len(detail["records"]), 2)
        self.assertEqual(detail["records"][0]["action"], "APPROVE")
        self.assertEqual(detail["records"][0]["comment"], "同意付款")
        self.assertIsNotNone(detail["duration_ms"])

        # 已办任务可以通过已办状态查询。
        handled_tasks = self.list_tasks(self.approver_a, status="APPROVED")
        self.assertEqual(len(handled_tasks), 1)
        self.assertEqual(handled_tasks[0]["id"], first_tasks[0]["id"])

    def test_reject_ends_instance_and_cancels_other_task(self) -> None:
        """任意一人拒绝后实例立即拒绝，其余待办不再出现在待办列表。"""

        process_id = self.publish_linear_process([self.approver_a, self.approver_b])
        self.start_instance(process_id)
        task = self.list_tasks(self.approver_a)[0]

        response = self.handle_task(task["id"], self.approver_a, "reject", comment="金额不符")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["data"]["instance_status"],
            INSTANCE_STATUS_REJECTED,
        )

        self.assertEqual(self.list_tasks(self.approver_b), [])
        cancelled_tasks = self.list_tasks(self.approver_b, status=TASK_STATUS_CANCELLED)
        self.assertEqual(len(cancelled_tasks), 1)

    def test_repeat_approval_returns_replay_result(self) -> None:
        """重复提交相同结果返回原结果并标记为重放。"""

        process_id = self.publish_linear_process([self.approver_a, self.approver_b])
        started = self.start_instance(process_id)
        task = self.list_tasks(self.approver_a)[0]

        self.handle_task(task["id"], self.approver_a, "approve")
        repeat_response = self.handle_task(task["id"], self.approver_a, "approve")

        self.assertEqual(repeat_response.status_code, 200, repeat_response.text)
        self.assertTrue(repeat_response.json()["data"]["idempotent_replay"])

        detail = self.client.get(
            f"/api/approval-instances/{started['instance_id']}"
        ).json()["data"]
        self.assertEqual(len(detail["records"]), 1)

    def test_conflicting_approval_returns_409(self) -> None:
        """同一任务被其他结果处理后再次提交返回 409。"""

        process_id = self.publish_linear_process([self.approver_a, self.approver_b])
        self.start_instance(process_id)
        task = self.list_tasks(self.approver_a)[0]
        self.handle_task(task["id"], self.approver_a, "approve")

        response = self.handle_task(task["id"], self.approver_a, "reject")
        self.assertEqual(response.status_code, 409)
        self.assertIn("已经被处理", response.json()["detail"])

    def test_other_person_approval_returns_403(self) -> None:
        """不是任务处理人的审批操作返回 403。"""

        process_id = self.publish_linear_process([self.approver_a])
        self.start_instance(process_id)
        task = self.list_tasks(self.approver_a)[0]

        response = self.handle_task(task["id"], self.approver_b, "approve")
        self.assertEqual(response.status_code, 403)

    def test_missing_task_returns_404(self) -> None:
        """处理不存在的审批任务返回 404。"""

        response = self.handle_task(str(uuid4()), self.approver_a, "approve")
        self.assertEqual(response.status_code, 404)

    def test_invalid_task_status_filter_returns_422(self) -> None:
        """不受支持的任务状态筛选值返回 422。"""

        response = self.client.get(
            "/api/approval-tasks",
            params={"person_id": str(self.approver_a), "status": "UNKNOWN"},
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
