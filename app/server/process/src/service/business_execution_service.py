"""业务执行记录创建与查询业务逻辑。

本服务在审批事务内被 ``ApprovalEngine.finish_instance()`` 调用。它只读取业务动作配置、
添加执行记录并 flush，不提交事务，也不发送任何外部 HTTP 请求。真正的调用由后台
Worker 在审批事务提交后执行，避免外部接口超时长期占用审批事务和数据库连接。
"""

from dataclasses import dataclass
from uuid import UUID

from sqlmodel import Session

from app.server.integration.src.models.business_action_model import BusinessAction
from app.server.integration.src.repository.business_action_repository import (
    BusinessActionRepository,
)
from app.server.process.src.constants import EXECUTION_STATUS_PENDING
from app.server.process.src.models.approval_model import ApprovalInstance
from app.server.process.src.models.execution_model import BusinessExecutionRecord
from app.server.process.src.repository.execution_repository import (
    BusinessExecutionRepository,
)
from app.server.process.src.service.exceptions import ExecutionRecordNotFoundError


@dataclass(frozen=True)
class ExecutionRecordView:
    """执行记录及其允许对外展示的关联信息。"""

    record: BusinessExecutionRecord


class BusinessExecutionService:
    """创建待执行的业务执行记录，并提供管理端查询能力。"""

    def __init__(
        self,
        repository: BusinessExecutionRepository | None = None,
        business_action_repository: BusinessActionRepository | None = None,
    ):
        """初始化业务执行服务并允许测试注入依赖。"""

        self.repository = repository or BusinessExecutionRepository()
        self.business_action_repository = (
            business_action_repository or BusinessActionRepository()
        )

    # ------------------------------------------------------------------
    # 审批事务内创建记录
    # ------------------------------------------------------------------

    def create_execution_record(
        self,
        instance: ApprovalInstance,
        db: Session,
    ) -> BusinessExecutionRecord | None:
        """审批通过、准备结束实例时创建唯一的待执行记录。

        只有配置了 action_code 的实例才产生执行记录。审批被拒绝、取消或还在运行中
        时不创建（拒绝走 reject_instance，不会调到本方法），只完成审批不触发业务的
        申请也不会创建。

        本方法只 write 当前 Session，调用方负责提交。记录创建失败时审批状态更新会随
        同一个事务一起回滚，不会出现审批已通过但没有执行任务的情况。

        特别注意：START → END 时租户使用记录可能还没有写入，因此这里既不解析租户
        配置，也不发送请求，一律交给事务提交后的后台执行器处理。
        """

        if not instance.action_code:
            return None

        # 数据库唯一约束是最终保障，这里提前返回已有记录避免重复插入。
        existing_record = self.repository.get_by_instance_id(instance.id, db)
        if existing_record is not None:
            return existing_record

        action = self.business_action_repository.get_by_code(instance.action_code, db)
        record = BusinessExecutionRecord(
            approval_instance_id=instance.id,
            **_build_action_snapshot(action),
            action_code=instance.action_code,
            request_payload_json=dict(instance.execution_payload_json or {}),
            status=EXECUTION_STATUS_PENDING,
        )
        self.repository.add(record, db)
        return record

    # ------------------------------------------------------------------
    # 管理端查询
    # ------------------------------------------------------------------

    def list_records(
        self,
        db: Session,
        approval_instance_id: UUID | None = None,
        action_code: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[BusinessExecutionRecord]:
        """按创建时间倒序查询执行记录，支持按实例、动作和状态筛选。"""

        return self.repository.list_records(
            db,
            approval_instance_id=approval_instance_id,
            action_code=action_code,
            status=status,
            offset=offset,
            limit=limit,
        )

    def get_record(self, record_id: UUID, db: Session) -> BusinessExecutionRecord:
        """查询单条执行记录，不存在时抛出领域异常。"""

        record = self.repository.get_by_id(record_id, db)
        if record is None:
            raise ExecutionRecordNotFoundError("业务执行记录不存在")
        return record


def _build_action_snapshot(action: BusinessAction | None) -> dict:
    """固化业务动作的调用配置快照。

    业务动作在审批期间被删除时返回空快照，由后台执行器判为配置缺失失败，而不是让
    已经完成的审批事务回滚，导致这条审批永远无法通过。
    """

    if action is None:
        return {
            "business_action_id": None,
            "http_method": None,
            "relative_path": None,
            "success_status_codes_json": None,
            "timeout_ms": None,
        }

    return {
        "business_action_id": action.id,
        # 动作停用不阻止执行：已经完成审批的任务继续使用创建记录时的配置。
        "http_method": action.http_method,
        "relative_path": action.relative_path,
        "success_status_codes_json": list(action.success_status_codes_json or []),
        "timeout_ms": action.timeout_ms,
    }
