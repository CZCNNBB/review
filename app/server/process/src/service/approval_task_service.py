"""审批任务查询、同意和拒绝业务逻辑。"""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlmodel import Session

from app.server.organization.src.service.organization_service import OrganizationService
from app.server.process.src.constants import (
    INSTANCE_STATUS_RUNNING,
    NODE_EXECUTION_STATUS_ACTIVE,
    RECORD_ACTION_APPROVE,
    RECORD_ACTION_REJECT,
    RECORD_ACTIONS,
    TASK_STATUS_BY_ACTION,
    TASK_STATUS_PENDING,
    TASK_STATUSES,
)
from app.server.process.src.engine.graph import build_version_graph
from app.server.process.src.engine.runner import (
    OUTCOME_APPROVED,
    OUTCOME_PENDING,
    OUTCOME_REJECTED,
    ApprovalEngine,
    resolve_approval_outcome,
)
from app.server.process.src.models.approval_model import (
    ApprovalInstance,
    ApprovalNodeExecution,
    ApprovalRecord,
    ApprovalTask,
)
from app.server.process.src.repository.approval_repository import ApprovalRepository
from app.server.process.src.repository.process_repository import ProcessRepository
from app.server.process.src.schemas.approval_schema import ApprovalTaskActionRequest
from app.server.process.src.service.exceptions import (
    ApprovalNotFoundError,
    ApprovalPermissionError,
    ApprovalStateError,
    ProcessStateError,
)


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""

    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class TaskListItem:
    """待办或已办列表中的一条任务，附带实例和节点展示信息。"""

    task: ApprovalTask
    instance_title: str
    business_key: str
    node_name: str


@dataclass(frozen=True)
class TaskActionView:
    """审批操作后的任务、节点和实例状态。"""

    instance: ApprovalInstance
    task: ApprovalTask
    node_execution: ApprovalNodeExecution
    current_node_execution: ApprovalNodeExecution | None
    idempotent_replay: bool


class ApprovalTaskService:
    """提供待办查询和审批人同意、拒绝操作。"""

    def __init__(
        self,
        repository: ApprovalRepository | None = None,
        process_repository: ProcessRepository | None = None,
        organization_service: OrganizationService | None = None,
        engine: ApprovalEngine | None = None,
    ):
        """初始化审批任务服务并允许测试注入依赖。"""

        self.repository = repository or ApprovalRepository()
        self.process_repository = process_repository or ProcessRepository()
        self.organization_service = organization_service or OrganizationService()
        self.engine = engine or ApprovalEngine(
            repository=self.repository,
            organization_service=self.organization_service,
        )

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_person_tasks(
        self,
        person_id: UUID,
        statuses: list[str],
        db: Session,
        offset: int = 0,
        limit: int = 100,
    ) -> list[TaskListItem]:
        """查询指定人员的待办或已办任务。"""

        tasks = self.repository.list_person_tasks(
            person_id,
            self.normalize_statuses(statuses),
            db,
            offset=offset,
            limit=limit,
        )
        if not tasks:
            return []

        instances = self.repository.list_instances_by_ids(
            list({task.instance_id for task in tasks}),
            db,
        )
        instances_by_id = {instance.id: instance for instance in instances}

        executions = self.repository.list_node_executions_by_ids(
            list({task.node_execution_id for task in tasks}),
            db,
        )
        executions_by_id = {execution.id: execution for execution in executions}

        items: list[TaskListItem] = []
        for task in tasks:
            instance = instances_by_id.get(task.instance_id)
            execution = executions_by_id.get(task.node_execution_id)
            items.append(
                TaskListItem(
                    task=task,
                    instance_title=instance.title if instance else "",
                    business_key=instance.business_key if instance else "",
                    node_name=execution.node_name if execution else "",
                )
            )
        return items

    # ------------------------------------------------------------------
    # 审批操作
    # ------------------------------------------------------------------

    def approve(
        self,
        task_id: UUID,
        request: ApprovalTaskActionRequest,
        db: Session,
    ) -> TaskActionView:
        """同意指定审批任务。"""

        return self.handle_task(task_id, RECORD_ACTION_APPROVE, request, db)

    def reject(
        self,
        task_id: UUID,
        request: ApprovalTaskActionRequest,
        db: Session,
    ) -> TaskActionView:
        """拒绝指定审批任务。"""

        return self.handle_task(task_id, RECORD_ACTION_REJECT, request, db)

    def handle_task(
        self,
        task_id: UUID,
        action: str,
        request: ApprovalTaskActionRequest,
        db: Session,
    ) -> TaskActionView:
        """在单个事务中完成一次审批操作并按 AND、OR 规则推进流程。

        先锁定审批实例，把同一实例上的并发审批操作串行化，保证 OR 模式只形成一个
        最终结果，也保证拒绝和同意不会同时推进流程。
        """

        if action not in RECORD_ACTIONS:
            raise ProcessStateError(f"不支持的审批动作：{action}")

        task_reference = self.repository.get_task_by_id(task_id, db)
        if task_reference is None:
            raise ApprovalNotFoundError("审批任务不存在")

        instance = self.repository.get_instance_for_update(
            task_reference.instance_id,
            db,
        )
        if instance is None:
            raise ApprovalNotFoundError("审批任务所属的审批实例不存在")

        task = self.repository.get_task_for_update(task_id, db)
        if task is None:
            raise ApprovalNotFoundError("审批任务不存在")
        if task.approver_person_id != request.person_id:
            raise ApprovalPermissionError("该审批任务不属于当前操作人")

        expected_status = TASK_STATUS_BY_ACTION[action]
        if task.status == expected_status:
            # 重复提交相同结果时返回原结果，不重复写审批记录。
            return self._build_action_view(instance, task, True, db)
        if task.status != TASK_STATUS_PENDING:
            raise ApprovalStateError("该审批任务已经被处理或取消，请刷新后重试")

        node_execution = self.repository.get_node_execution_by_id(
            task.node_execution_id,
            db,
        )
        if node_execution is None:
            raise ApprovalNotFoundError("审批任务所属的节点执行记录不存在")
        if instance.status != INSTANCE_STATUS_RUNNING:
            raise ApprovalStateError("审批实例已经结束，不能继续审批")
        if (
            instance.current_node_execution_id != node_execution.id
            or node_execution.status != NODE_EXECUTION_STATUS_ACTIVE
        ):
            raise ApprovalStateError("审批任务所在节点已经结束，不能继续审批")

        now = utc_now()
        self.repository.add_record(
            ApprovalRecord(
                instance_id=instance.id,
                node_execution_id=node_execution.id,
                task_id=task.id,
                operator_person_id=task.approver_person_id,
                operator_snapshot_json=dict(task.approver_snapshot_json or {}),
                action=action,
                comment=request.comment,
                created_at=now,
            ),
            db,
        )

        task.status = expected_status
        task.handled_at = now
        task.updated_at = now
        self.repository.add_task(task, db)

        try:
            self._apply_node_outcome(instance, node_execution, db)
            db.commit()
        except Exception:
            # 节点结果判定失败时不保留半成品状态，审批人可以刷新后重试。
            db.rollback()
            raise

        return self._build_action_view(instance, task, False, db)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _apply_node_outcome(
        self,
        instance: ApprovalInstance,
        node_execution: ApprovalNodeExecution,
        db: Session,
    ) -> None:
        """按 AND、OR 规则判断节点结果，并推进流程或结束实例。"""

        approval_mode = (node_execution.result_json or {}).get("approval_mode")
        if approval_mode not in {"AND", "OR"}:
            raise ProcessStateError("节点执行记录缺少审批模式，无法判断节点结果")

        node_tasks = self.repository.list_tasks_by_node_execution(node_execution.id, db)
        outcome = resolve_approval_outcome(
            approval_mode,
            [task.status for task in node_tasks],
        )

        if outcome == OUTCOME_PENDING:
            # 还有审批人没有处理，实例继续停在当前节点。
            return

        if outcome == OUTCOME_REJECTED:
            self.engine.reject_approval_node(instance, node_execution, db)
            return

        if outcome == OUTCOME_APPROVED:
            self.engine.continue_after_approval(
                instance,
                self._load_version_graph(instance, db),
                node_execution,
                db,
            )

    def _load_version_graph(
        self,
        instance: ApprovalInstance,
        db: Session,
    ):
        """读取实例绑定版本的运行期视图，审批通过后推进时使用。"""

        version = self.process_repository.get_version_by_id(
            instance.process_version_id,
            db,
        )
        if version is None:
            raise ProcessStateError("审批实例绑定的流程版本不存在")
        return build_version_graph(
            version,
            self.process_repository.list_nodes(version.id, db),
        )

    def _build_action_view(
        self,
        instance: ApprovalInstance,
        task: ApprovalTask,
        idempotent_replay: bool,
        db: Session,
    ) -> TaskActionView:
        """组装审批操作后的最新状态。"""

        node_execution = self.repository.get_node_execution_by_id(
            task.node_execution_id,
            db,
        )
        if node_execution is None:
            raise ApprovalNotFoundError("审批任务所属的节点执行记录不存在")

        current_node_execution = None
        if instance.current_node_execution_id is not None:
            current_node_execution = self.repository.get_node_execution_by_id(
                instance.current_node_execution_id,
                db,
            )

        return TaskActionView(
            instance=instance,
            task=task,
            node_execution=node_execution,
            current_node_execution=current_node_execution,
            idempotent_replay=idempotent_replay,
        )

    @staticmethod
    def normalize_statuses(statuses: list[str] | None) -> list[str]:
        """校验任务状态筛选值，返回可用于查询的列表。"""

        if not statuses:
            return []
        normalized: list[str] = []
        for status_value in statuses:
            if status_value not in TASK_STATUSES:
                supported_values = "、".join(TASK_STATUSES)
                raise ApprovalStateError(
                    f"任务状态 {status_value} 不受支持，可选值为 {supported_values}"
                )
            if status_value not in normalized:
                normalized.append(status_value)
        return normalized
