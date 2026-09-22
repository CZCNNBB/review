"""租户业务接入绑定与审批使用记录的数据访问实现。"""

from datetime import datetime
from uuid import UUID

from sqlmodel import Session, select

from app.server.tenant.src.models.tenant_model import (
    BusinessActionBinding,
    ProcessBinding,
    ProcessUsageRecord,
)


class TenantBindingRepository:
    """封装流程授权、业务动作授权和审批使用记录的数据库查询。"""

    # ------------------------------------------------------------------
    # 流程授权
    # ------------------------------------------------------------------

    def add_process_binding(self, binding: ProcessBinding, db: Session) -> None:
        """将流程授权加入当前数据库事务。"""

        db.add(binding)

    def get_process_binding_by_id(
        self,
        binding_id: UUID,
        db: Session,
    ) -> ProcessBinding | None:
        """按主键查询流程授权。"""

        return db.get(ProcessBinding, binding_id)

    def get_process_binding(
        self,
        tenant_id: UUID,
        process_id: UUID,
        db: Session,
    ) -> ProcessBinding | None:
        """按租户和流程查询授权。"""

        statement = select(ProcessBinding).where(
            ProcessBinding.tenant_id == tenant_id,
            ProcessBinding.process_id == process_id,
        )
        return db.exec(statement).first()

    def list_process_bindings(
        self,
        tenant_id: UUID,
        db: Session,
    ) -> list[ProcessBinding]:
        """按创建时间倒序查询租户的全部流程授权。"""

        statement = (
            select(ProcessBinding)
            .where(ProcessBinding.tenant_id == tenant_id)
            .order_by(ProcessBinding.created_at.desc())
        )
        return list(db.exec(statement).all())

    # ------------------------------------------------------------------
    # 业务动作授权
    # ------------------------------------------------------------------

    def add_business_action_binding(
        self,
        binding: BusinessActionBinding,
        db: Session,
    ) -> None:
        """将业务动作授权加入当前数据库事务。"""

        db.add(binding)

    def get_business_action_binding_by_id(
        self,
        binding_id: UUID,
        db: Session,
    ) -> BusinessActionBinding | None:
        """按主键查询业务动作授权。"""

        return db.get(BusinessActionBinding, binding_id)

    def get_business_action_binding(
        self,
        tenant_id: UUID,
        business_action_id: UUID,
        db: Session,
    ) -> BusinessActionBinding | None:
        """按租户和业务动作查询授权。"""

        statement = select(BusinessActionBinding).where(
            BusinessActionBinding.tenant_id == tenant_id,
            BusinessActionBinding.business_action_id == business_action_id,
        )
        return db.exec(statement).first()

    def list_business_action_bindings(
        self,
        tenant_id: UUID,
        db: Session,
    ) -> list[BusinessActionBinding]:
        """按创建时间倒序查询租户的全部业务动作授权。"""

        statement = (
            select(BusinessActionBinding)
            .where(BusinessActionBinding.tenant_id == tenant_id)
            .order_by(BusinessActionBinding.created_at.desc())
        )
        return list(db.exec(statement).all())

    # ------------------------------------------------------------------
    # 审批使用记录
    # ------------------------------------------------------------------

    def add_usage_record(self, record: ProcessUsageRecord, db: Session) -> None:
        """将审批使用记录加入当前数据库事务。"""

        db.add(record)

    def get_usage_record_by_id(
        self,
        record_id: UUID,
        db: Session,
    ) -> ProcessUsageRecord | None:
        """按主键查询审批使用记录。"""

        return db.get(ProcessUsageRecord, record_id)

    def get_usage_record_by_instance_id(
        self,
        approval_instance_id: UUID,
        db: Session,
    ) -> ProcessUsageRecord | None:
        """按审批实例查询使用记录，用于确认实例的租户归属。"""

        statement = select(ProcessUsageRecord).where(
            ProcessUsageRecord.approval_instance_id == approval_instance_id
        )
        return db.exec(statement).first()

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
    ) -> list[ProcessUsageRecord]:
        """按租户和可选筛选条件分页查询使用记录。

        查询条件始终包含 tenant_id，保证一个租户不会看到其他租户的使用记录。
        """

        statement = select(ProcessUsageRecord).where(
            ProcessUsageRecord.tenant_id == tenant_id
        )
        if process_id is not None:
            statement = statement.where(ProcessUsageRecord.process_id == process_id)
        if business_key:
            statement = statement.where(ProcessUsageRecord.business_key == business_key)
        if action_code:
            statement = statement.where(ProcessUsageRecord.action_code == action_code)
        if created_from is not None:
            statement = statement.where(ProcessUsageRecord.created_at >= created_from)
        if created_to is not None:
            statement = statement.where(ProcessUsageRecord.created_at <= created_to)

        statement = (
            statement.order_by(ProcessUsageRecord.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(db.exec(statement).all())
