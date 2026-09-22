"""业务接入相关的租户资源作用域测试。

覆盖业务接入模块新注册的三类资源在 TenantScope 中的差异：流程和业务动作绑定有启停
状态，审批使用记录没有状态且必须带上流程、版本和业务单据标识。
"""

import os
import unittest
from uuid import uuid4

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.common.scope import GlobalResourceScope
from app.server.integration.src.models.business_action_model import BusinessAction
from app.server.process.src.models.process_model import ApprovalProcess
from app.server.tenant.src.models.tenant_model import ProcessUsageRecord
from app.server.tenant.src.schemas.tenant_schema import TenantCreateRequest
from app.server.tenant.src.scope.business_access import create_business_access_context
from app.server.tenant.src.scope.tenant_scope import (
    RESOURCE_APPROVAL_INSTANCE,
    RESOURCE_BUSINESS_ACTION,
    RESOURCE_PROCESS,
    TenantResourceAccessError,
    TenantResourceScope,
    create_resource_scope,
)
from app.server.tenant.src.service.tenant_service import TenantService


class TenantBindingScopeTestCase(unittest.TestCase):
    """验证流程、业务动作和审批实例三类资源绑定行为。"""

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
                    "process": None,
                    "integration": None,
                }
            },
        )
        SQLModel.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.tenant_service = TenantService()
        self.previous_tenancy_enabled = os.environ.get("TENANCY_ENABLED")
        os.environ["TENANCY_ENABLED"] = "true"

        self.tenant = self.tenant_service.create_tenant(
            TenantCreateRequest(
                code="BUSINESS",
                name="业务系统",
                callback_base_url="https://business.example.com/approval",
            ),
            self.db,
        )

    def tearDown(self) -> None:
        """关闭数据库资源并恢复租户开关。"""

        self.db.close()
        self.engine.dispose()
        if self.previous_tenancy_enabled is None:
            os.environ.pop("TENANCY_ENABLED", None)
        else:
            os.environ["TENANCY_ENABLED"] = self.previous_tenancy_enabled

    def create_process(self) -> ApprovalProcess:
        """创建一条用于绑定的审批流。"""

        process = ApprovalProcess(name=f"流程-{uuid4().hex[:8]}")
        self.db.add(process)
        self.db.commit()
        self.db.refresh(process)
        return process

    def create_business_action(self) -> BusinessAction:
        """创建一个用于绑定的业务动作。"""

        action = BusinessAction(
            action_code=f"ACTION_{uuid4().hex[:8].upper()}",
            name="测试动作",
            http_method="POST",
            relative_path="/business/test-action",
            request_schema_json={"type": "object"},
            success_status_codes_json=[],
            timeout_ms=5000,
        )
        self.db.add(action)
        self.db.commit()
        self.db.refresh(action)
        return action

    def create_usage_record(self, **overrides) -> ProcessUsageRecord:
        """创建一条审批使用记录。"""

        values = {
            "tenant_id": self.tenant.id,
            "process_id": uuid4(),
            "process_version_id": uuid4(),
            "approval_instance_id": uuid4(),
            "business_key": f"BIZ-{uuid4().hex[:8]}",
        }
        values.update(overrides)

        record = ProcessUsageRecord(**values)
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    # ------------------------------------------------------------------
    # 有启停状态的资源
    # ------------------------------------------------------------------

    def test_process_scope_filters_and_checks_binding_status(self) -> None:
        """流程作用域只返回已启用的绑定，停用后拒绝访问。"""

        visible_process = self.create_process()
        hidden_process = self.create_process()

        scope = create_resource_scope(RESOURCE_PROCESS, self.tenant.id)
        scope.bind(visible_process.id, self.db)
        self.db.commit()

        statement = select(ApprovalProcess.id)
        visible_ids = list(
            self.db.exec(scope.apply_filter(statement, ApprovalProcess.id)).all()
        )
        self.assertEqual(visible_ids, [visible_process.id])

        scope.require_access(visible_process.id, self.db)
        with self.assertRaises(TenantResourceAccessError):
            scope.require_access(hidden_process.id, self.db)

        scope.unbind(visible_process.id, self.db)
        self.db.commit()

        with self.assertRaises(TenantResourceAccessError):
            scope.require_access(visible_process.id, self.db)

    def test_business_action_scope_reports_enabled_bindings(self) -> None:
        """业务动作作用域可以列出当前租户已启用的授权。"""

        action = self.create_business_action()
        scope = create_resource_scope(RESOURCE_BUSINESS_ACTION, self.tenant.id)
        scope.bind(action.id, self.db)
        self.db.commit()

        self.assertEqual(
            [binding.business_action_id for binding in scope.list_bindings(self.db)],
            [action.id],
        )
        self.assertEqual(len(scope.list_bindings(self.db, enabled_only=True)), 1)
        scope.require_access(action.id, self.db)

    def test_binding_is_reactivated_instead_of_duplicated(self) -> None:
        """重复绑定同一条流程时复用原记录，不产生与唯一约束冲突的新行。"""

        process = self.create_process()
        scope = create_resource_scope(RESOURCE_PROCESS, self.tenant.id)

        first_binding = scope.bind(process.id, self.db)
        self.db.commit()
        scope.unbind(process.id, self.db)
        self.db.commit()

        second_binding = scope.bind(process.id, self.db)
        self.db.commit()

        self.assertEqual(first_binding.id, second_binding.id)
        self.assertEqual(second_binding.status, "ENABLED")
        self.assertEqual(len(scope.list_bindings(self.db)), 1)

    # ------------------------------------------------------------------
    # 没有启停状态的使用记录
    # ------------------------------------------------------------------

    def test_usage_record_binding_requires_resource_attributes(self) -> None:
        """写入使用记录时必须提供流程、版本和业务单据标识。"""

        scope = create_resource_scope(RESOURCE_APPROVAL_INSTANCE, self.tenant.id)

        with self.assertRaises(ValueError):
            scope.bind(uuid4(), self.db, attributes={"process_id": uuid4()})

    def test_usage_record_scope_ignores_status_filter(self) -> None:
        """使用记录没有状态，存在即代表可以访问，启停筛选不影响结果。"""

        record = self.create_usage_record()
        scope = create_resource_scope(RESOURCE_APPROVAL_INSTANCE, self.tenant.id)

        scope.require_access(record.approval_instance_id, self.db)
        with self.assertRaises(TenantResourceAccessError):
            scope.require_access(uuid4(), self.db)

        # 停用操作对使用记录是空操作，历史记录不提供修改和删除。
        scope.unbind(record.approval_instance_id, self.db)
        self.db.commit()
        scope.require_access(record.approval_instance_id, self.db)

        statement = select(ProcessUsageRecord.id)
        visible_ids = list(
            self.db.exec(
                scope.apply_filter(statement, ProcessUsageRecord.approval_instance_id)
            ).all()
        )
        self.assertEqual(visible_ids, [record.id])
        self.assertEqual(
            scope.list_bindings(self.db, enabled_only=True)[0].id,
            record.id,
        )

    def test_existing_usage_record_cannot_be_overwritten_by_rebinding(self) -> None:
        """重复绑定审批实例时保留首次写入的历史归属信息。"""

        record = self.create_usage_record(action_code="PAYMENT_EXECUTE")
        original_values = {
            "process_id": record.process_id,
            "process_version_id": record.process_version_id,
            "business_key": record.business_key,
            "action_code": record.action_code,
        }
        scope = create_resource_scope(RESOURCE_APPROVAL_INSTANCE, self.tenant.id)

        rebound_record = scope.bind(
            record.approval_instance_id,
            self.db,
            attributes={
                "process_id": uuid4(),
                "process_version_id": uuid4(),
                "business_key": "BIZ-TAMPERED",
                "action_code": "REFUND_EXECUTE",
            },
        )
        self.db.commit()
        self.db.refresh(record)

        self.assertEqual(rebound_record.id, record.id)
        self.assertEqual(record.process_id, original_values["process_id"])
        self.assertEqual(
            record.process_version_id,
            original_values["process_version_id"],
        )
        self.assertEqual(record.business_key, original_values["business_key"])
        self.assertEqual(record.action_code, original_values["action_code"])

    def test_usage_record_is_visible_only_to_its_tenant(self) -> None:
        """使用记录按租户隔离，其他租户看不到也不可访问。"""

        other_tenant = self.tenant_service.create_tenant(
            TenantCreateRequest(
                code="OTHER",
                name="其他系统",
                callback_base_url="https://other.example.com/approval",
            ),
            self.db,
        )
        record = self.create_usage_record()

        other_scope = create_resource_scope(RESOURCE_APPROVAL_INSTANCE, other_tenant.id)
        with self.assertRaises(TenantResourceAccessError):
            other_scope.require_access(record.approval_instance_id, self.db)

        statement = select(ProcessUsageRecord.id)
        self.assertEqual(
            list(
                self.db.exec(
                    other_scope.apply_filter(
                        statement,
                        ProcessUsageRecord.approval_instance_id,
                    )
                ).all()
            ),
            [],
        )

    # ------------------------------------------------------------------
    # 业务接入上下文
    # ------------------------------------------------------------------

    def test_business_access_context_builds_three_tenant_scopes(self) -> None:
        """租户模式下业务接入上下文提供三个租户作用域。"""

        context = create_business_access_context(self.tenant.id)

        self.assertEqual(context.tenant_id, self.tenant.id)
        for scope in (
            context.process_scope,
            context.action_scope,
            context.instance_scope,
        ):
            self.assertIsInstance(scope, TenantResourceScope)

        self.assertEqual(context.process_scope.resource_type, RESOURCE_PROCESS)
        self.assertEqual(context.action_scope.resource_type, RESOURCE_BUSINESS_ACTION)
        self.assertEqual(
            context.instance_scope.resource_type,
            RESOURCE_APPROVAL_INSTANCE,
        )

    def test_business_access_context_is_no_op_in_global_mode(self) -> None:
        """全局模式下三个作用域都是空操作实现，且不需要 tenant_id。"""

        os.environ["TENANCY_ENABLED"] = "false"
        context = create_business_access_context(None)

        self.assertIsNone(context.tenant_id)
        for scope in (
            context.process_scope,
            context.action_scope,
            context.instance_scope,
        ):
            self.assertIsInstance(scope, GlobalResourceScope)

        statement = select(ApprovalProcess.id)
        self.assertIs(
            context.process_scope.apply_filter(statement, ApprovalProcess.id),
            statement,
        )
        context.process_scope.require_access(uuid4(), self.db)

        record_binding = context.instance_scope.bind(
            uuid4(),
            self.db,
            attributes={
                "process_id": uuid4(),
                "process_version_id": uuid4(),
                "business_key": "BIZ-GLOBAL",
            },
        )
        self.assertIsNone(record_binding)


if __name__ == "__main__":
    unittest.main()
