"""业务执行记录创建逻辑测试。

覆盖触发条件、动作配置快照、重复创建保护和事务边界。审批状态更新与执行记录创建必须
在同一个事务中成功或失败。
"""

import unittest
from uuid import uuid4

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.server.integration.src.models.business_action_model import BusinessAction
from app.server.process.src.constants import (
    END_RESULT_STATUS_APPROVED,
    END_RESULT_STATUS_REJECTED,
    EXECUTION_STATUS_PENDING,
)
from app.server.process.src.models.approval_model import ApprovalInstance
from app.server.process.src.models.execution_model import BusinessExecutionRecord
from app.server.process.src.service.business_execution_service import (
    BusinessExecutionService,
)
from app.server.process.src.service.exceptions import ExecutionRecordNotFoundError


class ExecutionRecordCreationTestCase(unittest.TestCase):
    """验证什么情况下创建 PENDING 执行记录，以及固化哪些配置。"""

    def setUp(self) -> None:
        """创建内存数据库并准备业务执行服务。"""

        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            # SQLite 没有 PostgreSQL Schema，测试时将各模块映射到默认命名空间。
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
        self.db = Session(self.engine)
        self.service = BusinessExecutionService()

    def tearDown(self) -> None:
        """关闭数据库会话。"""

        self.db.close()
        self.engine.dispose()

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def create_action(
        self,
        action_code: str,
        http_method: str = "POST",
        relative_path: str = "/internal/approval/payment",
        success_status_codes: list[int] | None = None,
        timeout_ms: int = 5000,
        status: str = "ENABLED",
    ) -> BusinessAction:
        """创建一条业务动作配置。"""

        action = BusinessAction(
            action_code=action_code,
            name=f"动作-{action_code}",
            http_method=http_method,
            relative_path=relative_path,
            success_status_codes_json=list(success_status_codes or []),
            timeout_ms=timeout_ms,
            status=status,
        )
        self.db.add(action)
        self.db.commit()
        return action

    def create_instance(
        self,
        action_code: str | None = "PAYMENT_EXECUTE",
        execution_payload: dict | None = None,
    ) -> ApprovalInstance:
        """创建一条审批实例。"""

        instance = ApprovalInstance(
            process_id=uuid4(),
            process_version_id=uuid4(),
            business_key=f"BIZ-{uuid4().hex[:8]}",
            idempotency_key=f"KEY-{uuid4().hex[:8]}",
            title="供应商付款申请",
            action_code=action_code,
            execution_payload_json=execution_payload or {"payment_id": "PAY-001"},
        )
        self.db.add(instance)
        self.db.commit()
        return instance

    def list_records(self) -> list[BusinessExecutionRecord]:
        """读取全部执行记录。"""

        return list(self.db.exec(select(BusinessExecutionRecord)).all())

    # ------------------------------------------------------------------
    # 触发条件
    # ------------------------------------------------------------------

    def test_approved_instance_with_action_code_creates_pending_record(self) -> None:
        """审批通过且配置了 action_code 时创建 PENDING 记录并固化动作配置。"""

        action = self.create_action(
            "PAYMENT_EXECUTE",
            http_method="PUT",
            relative_path="/internal/payment/execute",
            success_status_codes=[200, 202],
            timeout_ms=8000,
        )
        instance = self.create_instance()

        record = self.service.create_execution_record(
            instance,
            END_RESULT_STATUS_APPROVED,
            self.db,
        )
        self.db.commit()

        self.assertIsNotNone(record)
        self.assertEqual(record.status, EXECUTION_STATUS_PENDING)
        self.assertEqual(record.approval_instance_id, instance.id)
        self.assertEqual(record.business_action_id, action.id)
        self.assertEqual(record.action_code, "PAYMENT_EXECUTE")
        self.assertEqual(record.http_method, "PUT")
        self.assertEqual(record.relative_path, "/internal/payment/execute")
        self.assertEqual(record.success_status_codes_json, [200, 202])
        self.assertEqual(record.timeout_ms, 8000)
        self.assertEqual(record.request_payload_json, {"payment_id": "PAY-001"})
        # 请求地址要等后台执行器取得租户基础地址后再补齐。
        self.assertIsNone(record.request_url)
        self.assertIsNone(record.started_at)
        self.assertIsNone(record.finished_at)

    def test_instance_without_action_code_creates_nothing(self) -> None:
        """没有 action_code 表示只需要完成审批，不创建执行记录。"""

        instance = self.create_instance(action_code=None)

        record = self.service.create_execution_record(
            instance,
            END_RESULT_STATUS_APPROVED,
            self.db,
        )
        self.db.commit()

        self.assertIsNone(record)
        self.assertEqual(self.list_records(), [])

    def test_rejected_instance_creates_nothing(self) -> None:
        """审批被拒绝时不创建执行记录。"""

        self.create_action("PAYMENT_EXECUTE")
        instance = self.create_instance()

        record = self.service.create_execution_record(
            instance,
            END_RESULT_STATUS_REJECTED,
            self.db,
        )
        self.db.commit()

        self.assertIsNone(record)
        self.assertEqual(self.list_records(), [])

    def test_unknown_action_keeps_record_with_empty_snapshot(self) -> None:
        """业务动作配置缺失时仍然建记录，但快照留空交给执行器判定失败。

        这样审批可以正常结束，失败原因会体现在执行记录里，而不是让已经完成的审批事务
        回滚导致这条审批永远无法通过。
        """

        instance = self.create_instance(action_code="MISSING_ACTION")

        record = self.service.create_execution_record(
            instance,
            END_RESULT_STATUS_APPROVED,
            self.db,
        )
        self.db.commit()

        self.assertIsNotNone(record)
        self.assertEqual(record.status, EXECUTION_STATUS_PENDING)
        self.assertIsNone(record.business_action_id)
        self.assertIsNone(record.http_method)
        self.assertIsNone(record.relative_path)
        self.assertIsNone(record.timeout_ms)
        self.assertEqual(record.action_code, "MISSING_ACTION")

    def test_disabled_action_is_still_executed_from_snapshot(self) -> None:
        """动作停用不阻止已批准的调用，快照按动作原始配置固化。"""

        self.create_action("PAYMENT_EXECUTE", status="DISABLED")
        instance = self.create_instance()

        record = self.service.create_execution_record(
            instance,
            END_RESULT_STATUS_APPROVED,
            self.db,
        )
        self.db.commit()

        self.assertIsNotNone(record)
        self.assertEqual(record.http_method, "POST")
        self.assertIsNotNone(record.business_action_id)

    def test_approval_through_start_to_end_creates_record(self) -> None:
        """START → END(APPROVED) 直接结束时同样创建执行记录。

        这类流程不经过人工审批任务，因此创建点必须挂在统一结束入口上。
        """

        self.create_action("PAYMENT_EXECUTE")
        instance = self.create_instance()

        record = self.service.create_execution_record(
            instance,
            END_RESULT_STATUS_APPROVED,
            self.db,
        )
        self.db.commit()

        self.assertIsNotNone(record)
        self.assertEqual(record.status, EXECUTION_STATUS_PENDING)

    # ------------------------------------------------------------------
    # 重复创建保护
    # ------------------------------------------------------------------

    def test_same_instance_is_not_created_twice(self) -> None:
        """同一个审批实例最多产生一条执行记录。"""

        self.create_action("PAYMENT_EXECUTE")
        instance = self.create_instance()

        first_record = self.service.create_execution_record(
            instance,
            END_RESULT_STATUS_APPROVED,
            self.db,
        )
        self.db.commit()
        second_record = self.service.create_execution_record(
            instance,
            END_RESULT_STATUS_APPROVED,
            self.db,
        )
        self.db.commit()

        self.assertEqual(first_record.id, second_record.id)
        self.assertEqual(len(self.list_records()), 1)

    # ------------------------------------------------------------------
    # 事务边界
    # ------------------------------------------------------------------

    def test_record_and_approval_state_share_one_transaction(self) -> None:
        """审批状态更新和执行记录创建必须同事务成功或失败。"""

        self.create_action("PAYMENT_EXECUTE")
        instance = self.create_instance()

        instance.status = "APPROVED"
        self.db.add(instance)
        self.service.create_execution_record(
            instance,
            END_RESULT_STATUS_APPROVED,
            self.db,
        )
        # 模拟审批事务在提交前失败。
        self.db.rollback()

        self.db.expire_all()
        self.assertEqual(self.list_records(), [])
        reloaded_instance = self.db.get(ApprovalInstance, instance.id)
        self.assertEqual(reloaded_instance.status, "RUNNING")

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def test_filters_and_missing_record(self) -> None:
        """列表支持按实例、动作和状态筛选，详情找不到时抛出领域异常。"""

        self.create_action("PAYMENT_EXECUTE")
        self.create_action("ORDER_CONFIRM")
        first_instance = self.create_instance(action_code="PAYMENT_EXECUTE")
        second_instance = self.create_instance(action_code="ORDER_CONFIRM")

        self.service.create_execution_record(
            first_instance,
            END_RESULT_STATUS_APPROVED,
            self.db,
        )
        second_record = self.service.create_execution_record(
            second_instance,
            END_RESULT_STATUS_APPROVED,
            self.db,
        )
        self.db.commit()

        by_instance = self.service.list_records(
            self.db,
            approval_instance_id=first_instance.id,
        )
        self.assertEqual(len(by_instance), 1)
        self.assertEqual(by_instance[0].action_code, "PAYMENT_EXECUTE")

        by_action = self.service.list_records(self.db, action_code="ORDER_CONFIRM")
        self.assertEqual(len(by_action), 1)

        by_status = self.service.list_records(self.db, status=EXECUTION_STATUS_PENDING)
        self.assertEqual(len(by_status), 2)

        missing_status = self.service.list_records(self.db, status="SUCCEEDED")
        self.assertEqual(missing_status, [])

        self.assertEqual(
            self.service.get_record(second_record.id, self.db).id,
            second_record.id,
        )
        with self.assertRaises(ExecutionRecordNotFoundError):
            self.service.get_record(uuid4(), self.db)


if __name__ == "__main__":
    unittest.main()
