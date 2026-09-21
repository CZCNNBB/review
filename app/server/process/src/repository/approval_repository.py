"""审批实例、节点执行、审批任务和审批记录数据访问实现。"""

from datetime import datetime
from uuid import UUID

from sqlmodel import Session, func, select

from app.server.process.src.constants import (
    NODE_EXECUTION_STATUS_ACTIVE,
    TASK_STATUS_CANCELLED,
    TASK_STATUS_PENDING,
)
from app.server.process.src.models.approval_model import (
    ApprovalInstance,
    ApprovalNodeExecution,
    ApprovalRecord,
    ApprovalTask,
)


class ApprovalRepository:
    """封装审批运行数据的查询和状态写入。"""

    # ------------------------------------------------------------------
    # 审批实例
    # ------------------------------------------------------------------

    def add_instance(self, instance: ApprovalInstance, db: Session) -> None:
        """将审批实例加入当前事务。"""

        db.add(instance)

    def get_instance_by_id(
        self,
        instance_id: UUID,
        db: Session,
    ) -> ApprovalInstance | None:
        """按主键查询审批实例。"""

        return db.get(ApprovalInstance, instance_id)

    def get_instance_for_update(
        self,
        instance_id: UUID,
        db: Session,
    ) -> ApprovalInstance | None:
        """锁定并刷新审批实例，串行化同一实例上的并发审批操作。"""

        statement = (
            select(ApprovalInstance)
            .where(ApprovalInstance.id == instance_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return db.exec(statement).first()

    def get_instance_by_idempotency_key(
        self,
        idempotency_key: str,
        db: Session,
    ) -> ApprovalInstance | None:
        """按内部幂等键查询审批实例。"""

        statement = select(ApprovalInstance).where(
            ApprovalInstance.idempotency_key == idempotency_key
        )
        return db.exec(statement).first()

    def list_instances_by_ids(
        self,
        instance_ids: list[UUID],
        db: Session,
    ) -> list[ApprovalInstance]:
        """批量查询审批实例。"""

        if not instance_ids:
            return []
        statement = select(ApprovalInstance).where(
            ApprovalInstance.id.in_(instance_ids)
        )
        return list(db.exec(statement).all())

    # ------------------------------------------------------------------
    # 节点执行
    # ------------------------------------------------------------------

    def add_node_execution(
        self,
        execution: ApprovalNodeExecution,
        db: Session,
    ) -> None:
        """将节点执行记录加入当前事务。"""

        db.add(execution)

    def get_node_execution_by_id(
        self,
        execution_id: UUID,
        db: Session,
    ) -> ApprovalNodeExecution | None:
        """按主键查询节点执行记录。"""

        return db.get(ApprovalNodeExecution, execution_id)

    def get_active_node_execution(
        self,
        instance_id: UUID,
        db: Session,
    ) -> ApprovalNodeExecution | None:
        """查询实例当前的活动节点执行记录。"""

        statement = select(ApprovalNodeExecution).where(
            ApprovalNodeExecution.instance_id == instance_id,
            ApprovalNodeExecution.status == NODE_EXECUTION_STATUS_ACTIVE,
        )
        return db.exec(statement).first()

    def list_node_executions(
        self,
        instance_id: UUID,
        db: Session,
    ) -> list[ApprovalNodeExecution]:
        """按实际执行顺序查询实例经过的全部节点。"""

        statement = (
            select(ApprovalNodeExecution)
            .where(ApprovalNodeExecution.instance_id == instance_id)
            .order_by(ApprovalNodeExecution.sequence_no.asc())
        )
        return list(db.exec(statement).all())

    def list_node_executions_by_ids(
        self,
        execution_ids: list[UUID],
        db: Session,
    ) -> list[ApprovalNodeExecution]:
        """批量查询节点执行记录，供任务列表补充节点名称。"""

        if not execution_ids:
            return []
        statement = select(ApprovalNodeExecution).where(
            ApprovalNodeExecution.id.in_(execution_ids)
        )
        return list(db.exec(statement).all())

    def get_max_sequence_no(self, instance_id: UUID, db: Session) -> int:
        """查询实例当前最大执行顺序号，没有节点时返回零。"""

        statement = select(func.max(ApprovalNodeExecution.sequence_no)).where(
            ApprovalNodeExecution.instance_id == instance_id
        )
        return int(db.exec(statement).one() or 0)

    # ------------------------------------------------------------------
    # 审批任务
    # ------------------------------------------------------------------

    def add_task(self, task: ApprovalTask, db: Session) -> None:
        """将单个审批任务加入当前事务。"""

        db.add(task)

    def add_tasks(self, tasks: list[ApprovalTask], db: Session) -> None:
        """批量将审批任务加入当前事务。"""

        for task in tasks:
            db.add(task)

    def get_task_by_id(self, task_id: UUID, db: Session) -> ApprovalTask | None:
        """按主键查询审批任务。"""

        return db.get(ApprovalTask, task_id)

    def get_task_for_update(
        self,
        task_id: UUID,
        db: Session,
    ) -> ApprovalTask | None:
        """锁定并刷新审批任务，避免同一任务被并发处理。"""

        statement = (
            select(ApprovalTask)
            .where(ApprovalTask.id == task_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return db.exec(statement).first()

    def list_tasks_by_node_execution(
        self,
        node_execution_id: UUID,
        db: Session,
    ) -> list[ApprovalTask]:
        """按创建顺序查询某个节点下的全部审批任务。"""

        statement = (
            select(ApprovalTask)
            .where(ApprovalTask.node_execution_id == node_execution_id)
            .order_by(ApprovalTask.created_at.asc(), ApprovalTask.id.asc())
        )
        return list(db.exec(statement).all())

    def list_tasks_by_instance(
        self,
        instance_id: UUID,
        db: Session,
    ) -> list[ApprovalTask]:
        """按创建顺序查询实例下的全部审批任务。"""

        statement = (
            select(ApprovalTask)
            .where(ApprovalTask.instance_id == instance_id)
            .order_by(ApprovalTask.created_at.asc(), ApprovalTask.id.asc())
        )
        return list(db.exec(statement).all())

    def list_person_tasks(
        self,
        person_id: UUID,
        statuses: list[str],
        db: Session,
        offset: int,
        limit: int,
    ) -> list[ApprovalTask]:
        """按人员查询待办或已办任务，按创建时间倒序分页。"""

        statement = select(ApprovalTask).where(
            ApprovalTask.approver_person_id == person_id
        )
        if statuses:
            statement = statement.where(ApprovalTask.status.in_(statuses))
        statement = (
            statement.order_by(ApprovalTask.created_at.desc(), ApprovalTask.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(db.exec(statement).all())

    def cancel_task(self, task: ApprovalTask, now: datetime, db: Session) -> bool:
        """把待处理任务标记为被系统取消。

        只有 PENDING 任务可能被取消，已经处理的任务保持原状态，返回是否发生变更。
        """

        if task.status != TASK_STATUS_PENDING:
            return False

        task.status = TASK_STATUS_CANCELLED
        task.cancelled_at = now
        task.updated_at = now
        db.add(task)
        return True

    def cancel_pending_tasks_by_node(
        self,
        node_execution_id: UUID,
        now: datetime,
        db: Session,
    ) -> int:
        """取消某个节点下全部待处理任务，返回取消数量。"""

        return self._cancel_tasks(
            self.list_tasks_by_node_execution(node_execution_id, db),
            now,
            db,
        )

    def cancel_pending_tasks_by_instance(
        self,
        instance_id: UUID,
        now: datetime,
        db: Session,
    ) -> int:
        """取消整个实例下全部待处理任务，返回取消数量。"""

        return self._cancel_tasks(self.list_tasks_by_instance(instance_id, db), now, db)

    def _cancel_tasks(
        self,
        tasks: list[ApprovalTask],
        now: datetime,
        db: Session,
    ) -> int:
        """在内存对象上逐个取消任务，保持会话中的状态与数据库一致。"""

        return sum(1 for task in tasks if self.cancel_task(task, now, db))

    # ------------------------------------------------------------------
    # 审批记录
    # ------------------------------------------------------------------

    def add_record(self, record: ApprovalRecord, db: Session) -> None:
        """将不可变审批记录加入当前事务。"""

        db.add(record)

    def get_record_by_task_id(
        self,
        task_id: UUID,
        db: Session,
    ) -> ApprovalRecord | None:
        """按任务查询已产生的审批记录。"""

        statement = select(ApprovalRecord).where(ApprovalRecord.task_id == task_id)
        return db.exec(statement).first()

    def list_records_by_instance(
        self,
        instance_id: UUID,
        db: Session,
    ) -> list[ApprovalRecord]:
        """按操作时间查询实例下的全部审批记录。"""

        statement = (
            select(ApprovalRecord)
            .where(ApprovalRecord.instance_id == instance_id)
            .order_by(ApprovalRecord.created_at.asc(), ApprovalRecord.id.asc())
        )
        return list(db.exec(statement).all())
