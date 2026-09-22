"""业务执行记录数据访问实现。"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import update
from sqlmodel import Session, select

from app.server.process.src.constants import (
    EXECUTION_STATUS_PENDING,
    EXECUTION_STATUS_RUNNING,
)
from app.server.process.src.models.execution_model import BusinessExecutionRecord
from app.server.process.src.models.process_model import utc_now


class BusinessExecutionRepository:
    """封装业务执行记录的查询、领取和结果写入。"""

    def add(self, record: BusinessExecutionRecord, db: Session) -> None:
        """将执行记录加入当前事务。"""

        db.add(record)

    def get_by_id(
        self,
        record_id: UUID,
        db: Session,
    ) -> BusinessExecutionRecord | None:
        """按主键查询执行记录。"""

        return db.get(BusinessExecutionRecord, record_id)

    def get_by_instance_id(
        self,
        approval_instance_id: UUID,
        db: Session,
    ) -> BusinessExecutionRecord | None:
        """按审批实例查询执行记录，用于防止重复创建。"""

        statement = select(BusinessExecutionRecord).where(
            BusinessExecutionRecord.approval_instance_id == approval_instance_id
        )
        return db.exec(statement).first()

    def list_by_instance_ids(
        self,
        instance_ids: list[UUID],
        db: Session,
    ) -> list[BusinessExecutionRecord]:
        """批量查询审批实例对应的执行记录，供审批详情补充执行状态。"""

        if not instance_ids:
            return []
        statement = select(BusinessExecutionRecord).where(
            BusinessExecutionRecord.approval_instance_id.in_(instance_ids)
        )
        return list(db.exec(statement).all())

    def list_records(
        self,
        db: Session,
        approval_instance_id: UUID | None = None,
        action_code: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[BusinessExecutionRecord]:
        """按创建时间倒序分页查询执行记录，支持按实例、动作和状态筛选。"""

        statement = select(BusinessExecutionRecord)
        if approval_instance_id is not None:
            statement = statement.where(
                BusinessExecutionRecord.approval_instance_id == approval_instance_id
            )
        if action_code:
            statement = statement.where(
                BusinessExecutionRecord.action_code == action_code
            )
        if status:
            statement = statement.where(BusinessExecutionRecord.status == status)

        statement = (
            statement.order_by(
                BusinessExecutionRecord.created_at.desc(),
                BusinessExecutionRecord.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        return list(db.exec(statement).all())

    def claim_pending_records(
        self,
        batch_size: int,
        db: Session,
    ) -> list[BusinessExecutionRecord]:
        """领取最多 batch_size 条待执行记录并标记为 RUNNING。

        使用 PostgreSQL 的 FOR UPDATE SKIP LOCKED，多个应用进程同时轮询时一条任务只会
        被一个进程领取。领取必须是短事务：调用方在 HTTP 请求开始前提交事务释放行锁，
        不能拿着数据库锁等待外部接口返回。

        SQLite 测试环境会忽略 FOR UPDATE，此时依赖调用方串行领取。
        """

        statement = (
            select(BusinessExecutionRecord)
            .where(BusinessExecutionRecord.status == EXECUTION_STATUS_PENDING)
            .order_by(
                BusinessExecutionRecord.created_at.asc(),
                BusinessExecutionRecord.id.asc(),
            )
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        records = list(db.exec(statement).all())
        if not records:
            return []

        now = utc_now()
        for record in records:
            record.status = EXECUTION_STATUS_RUNNING
            record.started_at = now
            record.updated_at = now
            db.add(record)
        return records

    def save_result(
        self,
        record_id: UUID,
        status: str,
        request_url: str | None,
        http_status_code: int | None,
        response_body: str | None,
        error_message: str | None,
        finished_at: datetime,
        db: Session,
    ) -> bool:
        """把执行结果写回记录，返回是否真的更新了一行。

        更新条件带上 `status = 'RUNNING'`：只有被本进程领取中的记录才允许写最终状态，
        避免任何意外情况覆盖已经变化的状态。返回 False 说明记录不再是 RUNNING，调用方
        需要记录日志而不是静默忽略。
        """

        statement = (
            update(BusinessExecutionRecord)
            .where(
                BusinessExecutionRecord.id == record_id,
                BusinessExecutionRecord.status == EXECUTION_STATUS_RUNNING,
            )
            .values(
                status=status,
                request_url=request_url,
                http_status_code=http_status_code,
                response_body=response_body,
                error_message=error_message,
                finished_at=finished_at,
                updated_at=finished_at,
            )
        )
        result = db.execute(statement)
        db.commit()
        return result.rowcount == 1
