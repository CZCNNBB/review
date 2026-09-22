"""租户流程授权、业务动作授权和审批使用记录业务逻辑。

本模块是业务接入的管理侧能力：绑定前通过业务 Service 确认资源存在，不复制业务数据；
授权只表达使用权限，不覆盖流程节点、审批人配置或业务动作的调用配置。
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.server.integration.src.service.business_action_service import (
    BusinessActionService,
)
from app.server.process.src.service.approval_instance_service import (
    ApprovalInstanceService,
    InstanceOverview,
)
from app.server.process.src.service.process_service import ProcessService
from app.server.tenant.src.models.tenant_model import (
    BusinessActionBinding,
    ProcessBinding,
    ProcessUsageRecord,
    utc_now,
)
from app.server.tenant.src.repository.tenant_binding_repository import (
    TenantBindingRepository,
)
from app.server.tenant.src.service.exceptions import (
    TenantBindingConflictError,
    TenantBindingNotFoundError,
    TenantNotFoundError,
)
from app.server.tenant.src.service.tenant_service import TenantService


@dataclass(frozen=True)
class UsageRecordView:
    """使用记录及其从 process 运行表读取的运行摘要。"""

    record: ProcessUsageRecord
    overview: InstanceOverview | None


class TenantBindingService:
    """提供租户业务接入授权管理和审批使用记录查询能力。"""

    def __init__(
        self,
        repository: TenantBindingRepository | None = None,
        tenant_service: TenantService | None = None,
        process_service: ProcessService | None = None,
        business_action_service: BusinessActionService | None = None,
        approval_instance_service: ApprovalInstanceService | None = None,
    ):
        """初始化租户绑定服务并允许测试注入依赖。"""

        self.repository = repository or TenantBindingRepository()
        self.tenant_service = tenant_service or TenantService()
        self.process_service = process_service or ProcessService()
        self.business_action_service = business_action_service or BusinessActionService()
        self.approval_instance_service = (
            approval_instance_service or ApprovalInstanceService()
        )

    # ------------------------------------------------------------------
    # 流程授权
    # ------------------------------------------------------------------

    def create_process_binding(
        self,
        tenant_id: UUID,
        process_id: UUID,
        db: Session,
    ) -> ProcessBinding:
        """为租户授予流程使用权，重复调用返回同一条授权记录。

        授权记录不提供物理删除，因此已经停用的授权在这里重新启用，而不是插入一条
        与唯一约束冲突的新记录。
        """

        self._ensure_tenant_exists(tenant_id, db)
        # 通过业务 Service 确认流程存在，租户模块不直接读取 process 表。
        self.process_service.get_overview(process_id, db)

        existing_binding = self.repository.get_process_binding(tenant_id, process_id, db)
        if existing_binding:
            existing_binding.status = "ENABLED"
            existing_binding.updated_at = utc_now()
            self.repository.add_process_binding(existing_binding, db)
            db.commit()
            db.refresh(existing_binding)
            return existing_binding

        binding = ProcessBinding(tenant_id=tenant_id, process_id=process_id)
        self.repository.add_process_binding(binding, db)
        self._commit_or_conflict(db, "该租户已经绑定这条审批流")
        db.refresh(binding)
        return binding

    def list_process_bindings(
        self,
        tenant_id: UUID,
        db: Session,
    ) -> list[ProcessBinding]:
        """查询租户的全部流程授权。"""

        self._ensure_tenant_exists(tenant_id, db)
        return self.repository.list_process_bindings(tenant_id, db)

    def update_process_binding_status(
        self,
        tenant_id: UUID,
        binding_id: UUID,
        target_status: str,
        db: Session,
    ) -> ProcessBinding:
        """启用或停用流程授权，不物理删除记录。"""

        binding = self._get_tenant_process_binding(tenant_id, binding_id, db)
        binding.status = target_status
        binding.updated_at = utc_now()
        self.repository.add_process_binding(binding, db)
        db.commit()
        db.refresh(binding)
        return binding

    # ------------------------------------------------------------------
    # 业务动作授权
    # ------------------------------------------------------------------

    def create_business_action_binding(
        self,
        tenant_id: UUID,
        business_action_id: UUID,
        db: Session,
    ) -> BusinessActionBinding:
        """为租户授予业务动作使用权，重复调用返回同一条授权记录。"""

        self._ensure_tenant_exists(tenant_id, db)
        # 通过业务 Service 确认动作存在，租户模块不直接读取 integration 表。
        self.business_action_service.get_action(business_action_id, db)

        existing_binding = self.repository.get_business_action_binding(
            tenant_id,
            business_action_id,
            db,
        )
        if existing_binding:
            existing_binding.status = "ENABLED"
            existing_binding.updated_at = utc_now()
            self.repository.add_business_action_binding(existing_binding, db)
            db.commit()
            db.refresh(existing_binding)
            return existing_binding

        binding = BusinessActionBinding(
            tenant_id=tenant_id,
            business_action_id=business_action_id,
        )
        self.repository.add_business_action_binding(binding, db)
        self._commit_or_conflict(db, "该租户已经绑定这个业务动作")
        db.refresh(binding)
        return binding

    def list_business_action_bindings(
        self,
        tenant_id: UUID,
        db: Session,
    ) -> list[BusinessActionBinding]:
        """查询租户的全部业务动作授权。"""

        self._ensure_tenant_exists(tenant_id, db)
        return self.repository.list_business_action_bindings(tenant_id, db)

    def update_business_action_binding_status(
        self,
        tenant_id: UUID,
        binding_id: UUID,
        target_status: str,
        db: Session,
    ) -> BusinessActionBinding:
        """启用或停用业务动作授权，不物理删除记录。"""

        binding = self._get_tenant_business_action_binding(tenant_id, binding_id, db)
        binding.status = target_status
        binding.updated_at = utc_now()
        self.repository.add_business_action_binding(binding, db)
        db.commit()
        db.refresh(binding)
        return binding

    # ------------------------------------------------------------------
    # 审批使用记录
    # ------------------------------------------------------------------

    def list_usage_records(
        self,
        tenant_id: UUID,
        db: Session,
        process_id: UUID | None = None,
        business_key: str | None = None,
        action_code: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[UsageRecordView]:
        """按租户和筛选条件查询使用记录，并补充审批运行摘要。"""

        self._ensure_tenant_exists(tenant_id, db)
        records = self.repository.list_usage_records(
            tenant_id,
            db,
            process_id=process_id,
            business_key=business_key,
            action_code=action_code,
            created_from=created_from,
            created_to=created_to,
            offset=offset,
            limit=limit,
        )
        return self._attach_overviews(records, db)

    def get_usage_record(
        self,
        tenant_id: UUID,
        record_id: UUID,
        db: Session,
    ) -> UsageRecordView:
        """查询单条使用记录，记录不属于该租户时按不存在处理。"""

        record = self.repository.get_usage_record_by_id(record_id, db)
        if record is None or record.tenant_id != tenant_id:
            raise TenantBindingNotFoundError("审批使用记录不存在")

        views = self._attach_overviews([record], db)
        return views[0]

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _attach_overviews(
        self,
        records: list[ProcessUsageRecord],
        db: Session,
    ) -> list[UsageRecordView]:
        """批量补充审批运行摘要，避免逐条查询 process 表。"""

        overviews = self.approval_instance_service.list_instance_overviews(
            [record.approval_instance_id for record in records],
            db,
        )
        return [
            UsageRecordView(
                record=record,
                overview=overviews.get(record.approval_instance_id),
            )
            for record in records
        ]

    def _ensure_tenant_exists(self, tenant_id: UUID, db: Session) -> None:
        """确认租户存在，不存在时返回明确的未找到错误。"""

        tenant = self.tenant_service.get_tenant(tenant_id, db)
        if tenant is None:
            raise TenantNotFoundError("租户不存在")

    def _get_tenant_process_binding(
        self,
        tenant_id: UUID,
        binding_id: UUID,
        db: Session,
    ) -> ProcessBinding:
        """读取属于该租户的流程授权，避免跨租户修改其他租户的授权。"""

        binding = self.repository.get_process_binding_by_id(binding_id, db)
        if binding is None or binding.tenant_id != tenant_id:
            raise TenantBindingNotFoundError("流程授权不存在")
        return binding

    def _get_tenant_business_action_binding(
        self,
        tenant_id: UUID,
        binding_id: UUID,
        db: Session,
    ) -> BusinessActionBinding:
        """读取属于该租户的业务动作授权。"""

        binding = self.repository.get_business_action_binding_by_id(binding_id, db)
        if binding is None or binding.tenant_id != tenant_id:
            raise TenantBindingNotFoundError("业务动作授权不存在")
        return binding

    @staticmethod
    def _commit_or_conflict(db: Session, message: str) -> None:
        """提交事务，并将数据库唯一约束错误转换为领域冲突。"""

        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise TenantBindingConflictError(message) from exc
