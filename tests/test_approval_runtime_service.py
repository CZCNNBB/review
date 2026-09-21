"""审批运行 Service 集成测试，需要可用的 PostgreSQL 数据库。

覆盖发起审批、版本绑定、幂等处理、START 与 END 节点推进、AND 与 OR 多人审批、
条件分支选择和审批操作的并发保护。
"""

import threading
import unittest
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlmodel import Session

from app.server.organization.src.schemas.organization_schema import PersonCreateRequest
from app.server.organization.src.service.organization_service import OrganizationService
from app.server.process.src.constants import (
    INSTANCE_STATUS_APPROVED,
    INSTANCE_STATUS_ERROR,
    INSTANCE_STATUS_REJECTED,
    INSTANCE_STATUS_RUNNING,
    NODE_EXECUTION_STATUS_ACTIVE,
    NODE_EXECUTION_STATUS_COMPLETED,
    NODE_EXECUTION_STATUS_ERROR,
    NODE_EXECUTION_STATUS_REJECTED,
    NODE_TYPE_APPROVAL,
    NODE_TYPE_END,
    NODE_TYPE_START,
    TASK_STATUS_APPROVED,
    TASK_STATUS_CANCELLED,
    TASK_STATUS_PENDING,
    TASK_STATUS_REJECTED,
)
from app.server.process.src.schemas.approval_schema import (
    ApprovalStartRequest,
    ApprovalTaskActionRequest,
)
from app.server.process.src.schemas.process_schema import (
    ProcessCreateRequest,
    ProcessGraphNodeRequest,
    ProcessGraphSaveRequest,
)
from app.server.process.src.service.approval_instance_service import (
    ApprovalInstanceService,
)
from app.server.process.src.service.approval_task_service import ApprovalTaskService
from app.server.process.src.service.exceptions import (
    ApprovalConflictError,
    ApprovalPermissionError,
    ApprovalStateError,
    ProcessStateError,
    ProcessValidationError,
)
from app.server.process.src.service.process_service import ProcessService
from tests.process_test_helpers import (
    DatabaseTestCaseMixin,
    load_seed_node_definitions,
)


class ApprovalRuntimeServiceTestCase(DatabaseTestCaseMixin, unittest.TestCase):
    """验证审批实例推进和审批任务决策。"""

    def setUp(self) -> None:
        """准备数据库会话、服务、节点定义和测试人员。"""

        self.db: Session = self.open_session()
        self.process_service = ProcessService()
        self.instance_service = ApprovalInstanceService()
        self.task_service = ApprovalTaskService()
        self.seed = load_seed_node_definitions()

        self.applicant_id = self.create_person("运行测试发起人")
        self.approver_a = self.create_person("运行测试审批人A")
        self.approver_b = self.create_person("运行测试审批人B")
        self.approver_c = self.create_person("运行测试审批人C")

    def tearDown(self) -> None:
        """清理当前用例创建的数据。"""

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

    def build_start_node(self) -> ProcessGraphNodeRequest:
        """构造开始节点。"""

        return ProcessGraphNodeRequest(
            id=uuid4(),
            node_definition_id=self.seed[NODE_TYPE_START].id,
            name="开始",
            config={},
            position={"x": 100, "y": 100},
        )

    def build_approval_node(
        self,
        name: str,
        approver_person_ids: list[UUID],
        approval_mode: str = "AND",
    ) -> ProcessGraphNodeRequest:
        """构造人工审批节点。"""

        return ProcessGraphNodeRequest(
            id=uuid4(),
            node_definition_id=self.seed[NODE_TYPE_APPROVAL].id,
            name=name,
            config={
                "approval_mode": approval_mode,
                "approvers": [
                    {"person_id": str(person_id)} for person_id in approver_person_ids
                ],
            },
            position={"x": 300, "y": 100},
        )

    def build_end_node(self, result_status: str = "APPROVED") -> ProcessGraphNodeRequest:
        """构造结束节点。"""

        return ProcessGraphNodeRequest(
            id=uuid4(),
            node_definition_id=self.seed[NODE_TYPE_END].id,
            name=f"结束-{result_status}",
            config={"result_status": result_status},
            position={"x": 500, "y": 100},
        )

    def create_process(self, form_schema: dict[str, Any] | None = None) -> UUID:
        """创建流程和 V1 草稿并返回流程 ID。"""

        overview = self.process_service.create_process(
            ProcessCreateRequest(
                name=f"运行测试流程-{uuid4().hex[:8]}",
                form_schema=form_schema or {"type": "object", "properties": {}},
            ),
            self.db,
        )
        self.track_process(overview.process.id)
        return overview.process.id

    def save_and_publish(
        self,
        process_id: UUID,
        nodes: list[ProcessGraphNodeRequest],
        connections: list[dict],
        form_schema: dict[str, Any] | None = None,
    ) -> UUID:
        """把整图保存到当前草稿并发布，返回版本 ID。"""

        draft_version = self.process_service.repository.get_draft_version(
            process_id,
            self.db,
        )
        self.assertIsNotNone(draft_version)
        self.process_service.save_graph(
            draft_version.id,
            ProcessGraphSaveRequest(
                revision=draft_version.revision,
                name=draft_version.name,
                form_schema=form_schema or {"type": "object", "properties": {}},
                nodes=nodes,
                orchestration={"connections": connections},
            ),
            self.db,
        )
        self.process_service.publish_version(draft_version.id, self.db)
        return draft_version.id

    def publish_linear_process(
        self,
        approver_person_ids: list[UUID],
        approval_mode: str = "AND",
        form_schema: dict[str, Any] | None = None,
    ) -> tuple[UUID, dict[str, UUID]]:
        """发布 开始 → 人工审批 → 审批通过结束 的流程并返回流程 ID 和节点 ID。"""

        process_id = self.create_process(form_schema)
        start_node = self.build_start_node()
        approval_node = self.build_approval_node(
            "财务审批",
            approver_person_ids,
            approval_mode,
        )
        end_node = self.build_end_node()
        version_id = self.save_and_publish(
            process_id,
            [start_node, approval_node, end_node],
            [
                {
                    "source_node_id": str(start_node.id),
                    "target_node_id": str(approval_node.id),
                },
                {
                    "source_node_id": str(approval_node.id),
                    "target_node_id": str(end_node.id),
                },
            ],
            form_schema,
        )
        return process_id, {
            "version_id": version_id,
            "start": start_node.id,
            "approval": approval_node.id,
            "end": end_node.id,
        }

    def start_instance(
        self,
        process_id: UUID,
        business_key: str | None = None,
        approval_form: dict[str, Any] | None = None,
    ):
        """发起一次审批并返回发起结果。"""

        return self.instance_service.start_instance(
            process_id,
            ApprovalStartRequest(
                business_key=business_key or f"BIZ-{uuid4().hex[:8]}",
                title="供应商付款申请",
                applicant_person_id=self.applicant_id,
                action_code="PAYMENT_EXECUTE",
                approval_form=approval_form or {},
                execution_payload={"payment_id": "PAY-001"},
            ),
            self.db,
        )

    def get_instance_tasks(self, instance_id: UUID) -> list:
        """按审批人顺序返回实例下的全部任务。"""

        tasks = [
            task
            for task in self.task_service.repository.list_tasks_by_instance(
                instance_id,
                self.db,
            )
        ]
        return sorted(tasks, key=lambda task: str(task.approver_person_id))

    def get_pending_task(self, instance_id: UUID, person_id: UUID):
        """查询指定人员的待办任务。"""

        for item in self.task_service.list_person_tasks(
            person_id,
            [TASK_STATUS_PENDING],
            self.db,
        ):
            if item.task.instance_id == instance_id:
                return item.task
        return None

    def handle_task(
        self,
        task_id: UUID,
        person_id: UUID,
        action: str = "approve",
        comment: str | None = None,
    ):
        """同意或拒绝指定任务。"""

        request = ApprovalTaskActionRequest(person_id=person_id, comment=comment)
        if action == "approve":
            return self.task_service.approve(task_id, request, self.db)
        return self.task_service.reject(task_id, request, self.db)

    def get_instance(self, instance_id: UUID):
        """重新读取审批实例当前状态。

        会话里可能缓存了旧对象，这里强制刷新，保证断言看到的是库里的最新状态。
        """

        instance = self.instance_service.repository.get_instance_by_id(
            instance_id,
            self.db,
        )
        self.assertIsNotNone(instance)
        self.db.refresh(instance)
        return instance

    def run_concurrent_approvals(
        self,
        task_person_pairs: list[tuple[UUID, UUID]],
    ) -> tuple[list, list]:
        """在多个线程中同时同意审批任务，返回成功结果和异常。

        每个线程使用独立会话，模拟多位审批人同时提交操作。并发冲突属于预期结果，
        统一收集后由用例断言，避免线程里的异常只打印在控制台。
        """

        results: list = []
        errors: list = []
        barrier = threading.Barrier(len(task_person_pairs), timeout=10)

        def worker(task_id: UUID, person_id: UUID) -> None:
            """在独立会话中提交一次同意操作。"""

            try:
                with Session(self.engine) as session:
                    barrier.wait()
                    results.append(
                        ApprovalTaskService().approve(
                            task_id,
                            ApprovalTaskActionRequest(person_id=person_id),
                            session,
                        )
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=pair) for pair in task_person_pairs
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            self.assertFalse(thread.is_alive(), "并发审批线程未在超时时间内结束")
        return results, errors

    # ------------------------------------------------------------------
    # 发起审批
    # ------------------------------------------------------------------

    def test_start_creates_instance_and_first_tasks(self) -> None:
        """发起审批后实例停在人工审批节点并为全部审批人创建待办。"""

        process_id, node_ids = self.publish_linear_process(
            [self.approver_a, self.approver_b],
        )
        started = self.start_instance(process_id)

        self.assertEqual(started.instance.status, INSTANCE_STATUS_RUNNING)
        self.assertFalse(started.idempotent_replay)
        self.assertEqual(started.instance.process_version_id, node_ids["version_id"])
        self.assertEqual(
            started.current_node_execution.node_type,
            NODE_TYPE_APPROVAL,
        )
        self.assertEqual(
            set(started.pending_approver_person_ids),
            {self.approver_a, self.approver_b},
        )

        view = self.instance_service.get_instance_view(started.instance.id, self.db)
        self.assertEqual(
            [execution.node_type for execution in view.node_executions],
            [NODE_TYPE_START, NODE_TYPE_APPROVAL],
        )
        start_execution = view.node_executions[0]
        self.assertEqual(start_execution.status, NODE_EXECUTION_STATUS_COMPLETED)
        self.assertEqual(start_execution.next_node_id, node_ids["approval"])
        self.assertEqual(view.node_executions[1].status, NODE_EXECUTION_STATUS_ACTIVE)
        self.assertEqual(
            [task.status for task in view.tasks],
            [TASK_STATUS_PENDING, TASK_STATUS_PENDING],
        )

    def test_duplicate_start_returns_same_instance(self) -> None:
        """相同幂等键重复发起时返回原审批实例，不重复创建任务。"""

        process_id, _ = self.publish_linear_process(
            [self.approver_a, self.approver_b],
        )
        business_key = f"BIZ-{uuid4().hex[:8]}"
        first = self.start_instance(process_id, business_key=business_key)
        second = self.start_instance(process_id, business_key=business_key)

        self.assertTrue(second.idempotent_replay)
        self.assertEqual(first.instance.id, second.instance.id)
        self.assertEqual(
            len(self.get_instance_tasks(first.instance.id)),
            2,
        )

    def test_same_business_key_with_changed_content_is_rejected(self) -> None:
        """同一业务单据提交不同审批内容时返回冲突，不静默返回旧实例。"""

        process_id, _ = self.publish_linear_process([self.approver_a])
        business_key = f"BIZ-{uuid4().hex[:8]}"
        self.start_instance(
            process_id,
            business_key=business_key,
            approval_form={"amount": 100},
        )

        with self.assertRaises(ApprovalConflictError):
            self.start_instance(
                process_id,
                business_key=business_key,
                approval_form={"amount": 999},
            )

    def test_same_business_key_with_changed_payload_is_rejected(self) -> None:
        """业务执行参数变化同样按请求内容变化处理。"""

        process_id, _ = self.publish_linear_process([self.approver_a])
        business_key = f"BIZ-{uuid4().hex[:8]}"
        self.start_instance(process_id, business_key=business_key)

        changed_request = ApprovalStartRequest(
            business_key=business_key,
            title="供应商付款申请",
            applicant_person_id=self.applicant_id,
            action_code="PAYMENT_EXECUTE",
            approval_form={},
            execution_payload={"payment_id": "PAY-002"},
        )
        with self.assertRaises(ApprovalConflictError):
            self.instance_service.start_instance(process_id, changed_request, self.db)

    def test_instance_binds_published_version(self) -> None:
        """流程发布新版本后，运行中的实例继续使用原版本。"""

        process_id, first_node_ids = self.publish_linear_process([self.approver_a])
        first_instance = self.start_instance(process_id, business_key="BIZ-OLD")

        # 复制出 V2 草稿并把审批人换成另一位，然后发布。
        draft_version = self.process_service.create_draft(process_id, self.db)
        start_node = self.build_start_node()
        approval_node = self.build_approval_node("财务审批-V2", [self.approver_b])
        end_node = self.build_end_node()
        self.save_and_publish(
            process_id,
            [start_node, approval_node, end_node],
            [
                {
                    "source_node_id": str(start_node.id),
                    "target_node_id": str(approval_node.id),
                },
                {
                    "source_node_id": str(approval_node.id),
                    "target_node_id": str(end_node.id),
                },
            ],
        )
        second_instance = self.start_instance(process_id, business_key="BIZ-NEW")

        self.assertEqual(first_instance.instance.process_version_id, first_node_ids["version_id"])
        self.assertNotEqual(
            second_instance.instance.process_version_id,
            first_node_ids["version_id"],
        )
        self.assertEqual(second_instance.version.version_no, 2)

        first_tasks = self.get_instance_tasks(first_instance.instance.id)
        self.assertEqual(
            {task.approver_person_id for task in first_tasks},
            {self.approver_a},
        )
        second_tasks = self.get_instance_tasks(second_instance.instance.id)
        self.assertEqual(
            {task.approver_person_id for task in second_tasks},
            {self.approver_b},
        )
        self.assertIsNotNone(draft_version)

    def test_start_requires_published_process(self) -> None:
        """尚未发布的流程不能发起审批。"""

        process_id = self.create_process()
        with self.assertRaises(ProcessStateError):
            self.start_instance(process_id)

    def test_start_validates_approval_form(self) -> None:
        """审批单数据不符合版本表单 Schema 时拒绝发起。"""

        form_schema = {
            "type": "object",
            "required": ["amount"],
            "properties": {"amount": {"type": "number"}},
        }
        process_id, _ = self.publish_linear_process(
            [self.approver_a],
            form_schema=form_schema,
        )
        with self.assertRaises(ProcessValidationError) as context:
            self.start_instance(process_id, approval_form={"amount": "很多"})

        self.assertTrue(context.exception.issues)
        self.assertEqual(context.exception.issues[0].field, "approval_form.amount")

    # ------------------------------------------------------------------
    # AND 与 OR 决策
    # ------------------------------------------------------------------

    def test_and_mode_waits_for_every_approver(self) -> None:
        """AND 模式必须全部审批人同意后节点才通过。"""

        process_id, node_ids = self.publish_linear_process(
            [self.approver_a, self.approver_b],
        )
        started = self.start_instance(process_id)
        instance_id = started.instance.id

        first_task = self.get_pending_task(instance_id, self.approver_a)
        self.handle_task(first_task.id, self.approver_a, comment="同意")

        instance = self.get_instance(instance_id)
        self.assertEqual(instance.status, INSTANCE_STATUS_RUNNING)
        self.assertEqual(
            self.get_instance(instance_id).current_node_execution_id,
            started.current_node_execution.id,
        )
        self.assertEqual(self.get_pending_task(instance_id, self.approver_b).status, TASK_STATUS_PENDING)

        second_task = self.get_pending_task(instance_id, self.approver_b)
        self.handle_task(second_task.id, self.approver_b)

        instance = self.get_instance(instance_id)
        self.assertEqual(instance.status, INSTANCE_STATUS_APPROVED)
        self.assertIsNotNone(instance.finished_at)
        self.assertIsNone(instance.current_node_execution_id)

        view = self.instance_service.get_instance_view(instance_id, self.db)
        self.assertEqual(
            [execution.node_type for execution in view.node_executions],
            [NODE_TYPE_START, NODE_TYPE_APPROVAL, NODE_TYPE_END],
        )
        self.assertEqual(view.node_executions[1].status, NODE_EXECUTION_STATUS_COMPLETED)
        self.assertEqual(view.node_executions[2].node_id, node_ids["end"])
        self.assertEqual(
            [task.status for task in view.tasks],
            [TASK_STATUS_APPROVED, TASK_STATUS_APPROVED],
        )
        self.assertEqual([record.action for record in view.records], ["APPROVE", "APPROVE"])

    def test_reject_ends_instance_and_cancels_remaining_tasks(self) -> None:
        """任意一人拒绝后实例立即拒绝，其余待办全部取消。"""

        process_id, _ = self.publish_linear_process(
            [self.approver_a, self.approver_b],
        )
        started = self.start_instance(process_id)
        instance_id = started.instance.id

        reject_task = self.get_pending_task(instance_id, self.approver_a)
        self.handle_task(reject_task.id, self.approver_a, action="reject", comment="金额不符")

        instance = self.get_instance(instance_id)
        self.assertEqual(instance.status, INSTANCE_STATUS_REJECTED)
        self.assertIsNone(instance.current_node_execution_id)

        view = self.instance_service.get_instance_view(instance_id, self.db)
        self.assertEqual(len(view.node_executions), 2)
        self.assertEqual(
            view.node_executions[1].status,
            NODE_EXECUTION_STATUS_REJECTED,
        )
        self.assertEqual(
            sorted(task.status for task in view.tasks),
            sorted([TASK_STATUS_REJECTED, TASK_STATUS_CANCELLED]),
        )
        self.assertIsNone(self.get_pending_task(instance_id, self.approver_b))

    def test_or_mode_first_approval_cancels_other_tasks(self) -> None:
        """OR 模式第一个同意结果决定节点通过，其余待办取消。"""

        process_id, _ = self.publish_linear_process(
            [self.approver_a, self.approver_b, self.approver_c],
            approval_mode="OR",
        )
        started = self.start_instance(process_id)
        instance_id = started.instance.id

        approve_task = self.get_pending_task(instance_id, self.approver_b)
        self.handle_task(approve_task.id, self.approver_b)

        instance = self.get_instance(instance_id)
        self.assertEqual(instance.status, INSTANCE_STATUS_APPROVED)

        statuses = [task.status for task in self.get_instance_tasks(instance_id)]
        self.assertEqual(statuses.count(TASK_STATUS_APPROVED), 1)
        self.assertEqual(statuses.count(TASK_STATUS_CANCELLED), 2)

    def test_repeat_approval_returns_same_result(self) -> None:
        """重复提交相同结果时返回原结果，不重复写审批记录。"""

        process_id, _ = self.publish_linear_process(
            [self.approver_a, self.approver_b],
            approval_mode="OR",
        )
        started = self.start_instance(process_id)
        instance_id = started.instance.id
        task = self.get_pending_task(instance_id, self.approver_a)

        first = self.handle_task(task.id, self.approver_a)
        second = self.handle_task(task.id, self.approver_a)

        self.assertFalse(first.idempotent_replay)
        self.assertTrue(second.idempotent_replay)
        self.assertEqual(second.task.status, TASK_STATUS_APPROVED)

        view = self.instance_service.get_instance_view(instance_id, self.db)
        self.assertEqual(len(view.records), 1)

    def test_handled_task_with_other_result_is_rejected(self) -> None:
        """任务已经被其他结果处理时再次提交返回状态冲突。"""

        process_id, _ = self.publish_linear_process(
            [self.approver_a, self.approver_b],
        )
        started = self.start_instance(process_id)
        instance_id = started.instance.id
        task = self.get_pending_task(instance_id, self.approver_a)
        self.handle_task(task.id, self.approver_a)

        with self.assertRaises(ApprovalStateError):
            self.handle_task(task.id, self.approver_a, action="reject")

    def test_other_person_cannot_handle_task(self) -> None:
        """审批人只能处理分配给自己的待办任务。"""

        process_id, _ = self.publish_linear_process([self.approver_a])
        started = self.start_instance(process_id)
        task = self.get_pending_task(started.instance.id, self.approver_a)

        with self.assertRaises(ApprovalPermissionError):
            self.handle_task(task.id, self.approver_c)

    # ------------------------------------------------------------------
    # 并发控制
    # ------------------------------------------------------------------

    def test_concurrent_approvals_form_single_node_result(self) -> None:
        """OR 模式下并发同意不同任务只形成一个最终结果。"""

        process_id, _ = self.publish_linear_process(
            [self.approver_a, self.approver_b],
            approval_mode="OR",
        )
        started = self.start_instance(process_id)
        instance_id = started.instance.id
        first_task = self.get_pending_task(instance_id, self.approver_a)
        second_task = self.get_pending_task(instance_id, self.approver_b)

        results, errors = self.run_concurrent_approvals(
            [(first_task.id, self.approver_a), (second_task.id, self.approver_b)],
        )

        self.assertEqual(len(results) + len(errors), 2)
        for error in errors:
            # 后到的操作看到节点已经结束，返回可重试的状态冲突。
            self.assertIsInstance(error, ApprovalStateError)

        records = self.task_service.repository.list_records_by_instance(
            instance_id,
            self.db,
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(self.get_instance(instance_id).status, INSTANCE_STATUS_APPROVED)

    def test_concurrent_same_task_writes_single_record(self) -> None:
        """同一任务被并发提交相同结果时只写一条审批记录。"""

        process_id, _ = self.publish_linear_process(
            [self.approver_a, self.approver_b],
        )
        started = self.start_instance(process_id)
        instance_id = started.instance.id
        task = self.get_pending_task(instance_id, self.approver_a)

        results, errors = self.run_concurrent_approvals(
            [(task.id, self.approver_a), (task.id, self.approver_a)],
        )

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        # 后到的一次按重复提交处理，返回原结果而不是再写一条记录。
        self.assertEqual(
            sorted(result.idempotent_replay for result in results),
            [False, True],
        )

        records = self.task_service.repository.list_records_by_instance(
            instance_id,
            self.db,
        )
        self.assertEqual(len(records), 1)

    # ------------------------------------------------------------------
    # 条件分支
    # ------------------------------------------------------------------

    def publish_branch_process(self) -> tuple[UUID, dict[str, UUID]]:
        """发布带条件分支的流程。

        财务审批按金额选择后续路径：金额超过阈值时进入总经理审批后通过，未超过阈值
        时走默认路径进入拒绝结束节点。版本校验要求至少存在一个通过结束节点，因此
        拒绝出口必须和通过出口并存。
        """

        form_schema = {
            "type": "object",
            "properties": {"amount": {"type": "number"}},
        }
        process_id = self.create_process(form_schema)
        start_node = self.build_start_node()
        finance_node = self.build_approval_node("财务审批", [self.approver_a])
        manager_node = self.build_approval_node("总经理审批", [self.approver_b])
        approved_end_node = self.build_end_node("APPROVED")
        rejected_end_node = self.build_end_node("REJECTED")
        version_id = self.save_and_publish(
            process_id,
            [start_node, finance_node, manager_node, approved_end_node, rejected_end_node],
            [
                {
                    "source_node_id": str(start_node.id),
                    "target_node_id": str(finance_node.id),
                },
                {
                    "source_node_id": str(finance_node.id),
                    "target_node_id": str(manager_node.id),
                    "condition": {
                        "field": "approval_form.amount",
                        "operator": "GT",
                        "value": 1000,
                    },
                },
                {
                    "source_node_id": str(finance_node.id),
                    "target_node_id": str(rejected_end_node.id),
                    "default": True,
                },
                {
                    "source_node_id": str(manager_node.id),
                    "target_node_id": str(approved_end_node.id),
                },
            ],
            form_schema,
        )
        return process_id, {
            "version_id": version_id,
            "finance": finance_node.id,
            "manager": manager_node.id,
            "approved_end": approved_end_node.id,
            "rejected_end": rejected_end_node.id,
        }

    def test_condition_branch_selects_matching_path(self) -> None:
        """金额超过阈值时走条件分支，否则走默认路径。"""

        process_id, node_ids = self.publish_branch_process()

        large_started = self.start_instance(
            process_id,
            business_key="BIZ-LARGE",
            approval_form={"amount": 5000},
        )
        finance_task = self.get_pending_task(large_started.instance.id, self.approver_a)
        self.handle_task(finance_task.id, self.approver_a)

        large_view = self.instance_service.get_instance_view(
            large_started.instance.id,
            self.db,
        )
        self.assertEqual(
            [execution.node_type for execution in large_view.node_executions],
            [NODE_TYPE_START, NODE_TYPE_APPROVAL, NODE_TYPE_APPROVAL],
        )
        finance_execution = large_view.node_executions[1]
        self.assertEqual(finance_execution.node_id, node_ids["finance"])
        self.assertEqual(finance_execution.next_node_id, node_ids["manager"])
        self.assertTrue(finance_execution.result_json["condition_hit"])

        manager_task = self.get_pending_task(large_started.instance.id, self.approver_b)
        self.handle_task(manager_task.id, self.approver_b)
        self.assertEqual(
            self.get_instance(large_started.instance.id).status,
            INSTANCE_STATUS_APPROVED,
        )

    def test_default_path_is_used_when_condition_misses(self) -> None:
        """条件未命中时走默认路径，进入拒绝结束节点。"""

        process_id, node_ids = self.publish_branch_process()
        started = self.start_instance(
            process_id,
            business_key="BIZ-SMALL",
            approval_form={"amount": 100},
        )
        finance_task = self.get_pending_task(started.instance.id, self.approver_a)
        self.handle_task(finance_task.id, self.approver_a)

        view = self.instance_service.get_instance_view(started.instance.id, self.db)
        self.assertEqual(
            [execution.node_type for execution in view.node_executions],
            [NODE_TYPE_START, NODE_TYPE_APPROVAL, NODE_TYPE_END],
        )
        finance_execution = view.node_executions[1]
        self.assertEqual(finance_execution.next_node_id, node_ids["rejected_end"])
        self.assertFalse(finance_execution.result_json["condition_hit"])
        self.assertEqual(
            self.get_instance(started.instance.id).status,
            INSTANCE_STATUS_REJECTED,
        )

    # ------------------------------------------------------------------
    # 异常数据兜底
    # ------------------------------------------------------------------

    def test_corrupt_version_marks_instance_error(self) -> None:
        """审批通过后发现编排不可用时实例置为 ERROR，不留下卡住的运行中实例。"""

        process_id, node_ids = self.publish_linear_process([self.approver_a])
        started = self.start_instance(process_id)
        instance_id = started.instance.id
        task = self.get_pending_task(instance_id, self.approver_a)

        # 直接改库模拟已发布版本在运行期间被破坏：审批节点不再有任何后续连线。
        self.db.execute(
            text(
                "UPDATE process.approval_process_version "
                "SET orchestration_json = CAST(:payload AS JSONB) WHERE id = :version_id"
            ),
            {"payload": '{"connections": []}', "version_id": str(node_ids["version_id"])},
        )
        self.db.commit()

        self.handle_task(task.id, self.approver_a)

        instance = self.get_instance(instance_id)
        self.assertEqual(instance.status, INSTANCE_STATUS_ERROR)
        self.assertIsNotNone(instance.finished_at)
        self.assertIsNone(instance.current_node_execution_id)

        view = self.instance_service.get_instance_view(instance_id, self.db)
        # 审批人的操作已经留痕，节点执行和实例都被明确标记为异常。
        self.assertEqual(view.tasks[0].status, TASK_STATUS_APPROVED)
        self.assertEqual(len(view.records), 1)
        self.assertEqual(view.node_executions[1].status, NODE_EXECUTION_STATUS_ERROR)
        self.assertIn("error", view.node_executions[1].result_json)

    # ------------------------------------------------------------------
    # 待办查询
    # ------------------------------------------------------------------

    def test_person_task_list_exposes_instance_context(self) -> None:
        """待办列表带上实例标题、业务单号和节点名称。"""

        process_id, _ = self.publish_linear_process([self.approver_a])
        started = self.start_instance(process_id, business_key="BIZ-TODO")

        items = self.task_service.list_person_tasks(
            self.approver_a,
            [TASK_STATUS_PENDING],
            self.db,
        )
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.task.instance_id, started.instance.id)
        self.assertEqual(item.business_key, "BIZ-TODO")
        self.assertEqual(item.instance_title, "供应商付款申请")
        self.assertEqual(item.node_name, "财务审批")


if __name__ == "__main__":
    unittest.main()
