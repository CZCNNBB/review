"""审批实例推进引擎：节点进入、流程推进、结束与失败。

引擎只负责按已发布版本的编排推进入口节点，不处理审批人的具体操作。人工审批节点
会为全部审批人创建待办任务并停下，等任务服务形成节点结果后再从这里继续推进。

节点的具体行为按类型拆在 ``engine/nodes/`` 下，类型清单与处理器注册表在
``nodes/registry.py``；本文件只剩引擎本体（调度循环与各类推进辅助）。
"""

from typing import Mapping, Sequence
from uuid import UUID

from sqlmodel import Session

from app.server.process.src.constants import (
    INSTANCE_STATUS_APPROVED,
    INSTANCE_STATUS_ERROR,
    INSTANCE_STATUS_REJECTED,
    MAX_ADVANCE_STEPS,
    NODE_EXECUTION_STATUS_ACTIVE,
    NODE_EXECUTION_STATUS_COMPLETED,
    NODE_EXECUTION_STATUS_ERROR,
    NODE_EXECUTION_STATUS_REJECTED,
    TASK_STATUS_PENDING,
)
from app.server.organization.src.service.organization_service import OrganizationService
from app.server.process.src.engine.condition import select_next_connection
from app.server.process.src.engine.graph import VersionGraph
from app.server.process.src.engine.nodes.approval import (
    OUTCOME_APPROVED,
    OUTCOME_REJECTED,
)
from app.server.process.src.engine.nodes.base import NodeContext
from app.server.process.src.engine.nodes.registry import NODE_HANDLERS
from app.server.process.src.models.approval_model import (
    ApprovalInstance,
    ApprovalNodeExecution,
    ApprovalTask,
)
from app.server.process.src.models.process_model import (
    ApprovalProcessVersionNode,
    utc_now,
)
from app.server.process.src.repository.approval_repository import ApprovalRepository
from app.server.process.src.service.business_execution_service import (
    BusinessExecutionService,
)
from app.server.process.src.service.exceptions import ProcessStateError


class ApprovalEngine:
    """按版本编排推进审批实例，并维护节点执行记录和人工待办任务。"""

    def __init__(
        self,
        repository: ApprovalRepository | None = None,
        organization_service: OrganizationService | None = None,
        business_execution_service: BusinessExecutionService | None = None,
    ):
        """初始化推进引擎并允许测试注入依赖。

        业务执行属于 process 内部子模块，引擎直接持有同模块的业务执行服务，不需要
        跨模块端口。单元测试可以注入测试替身，保持推进逻辑可以独立验证。
        """

        self.repository = repository or ApprovalRepository()
        self.organization_service = organization_service or OrganizationService()
        self.business_execution_service = (
            business_execution_service or BusinessExecutionService()
        )

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------

    def start_instance(
        self,
        instance: ApprovalInstance,
        graph: VersionGraph,
        db: Session,
    ) -> None:
        """从开始节点推进实例，直到进入人工审批节点或实例结束。"""

        self._run(instance, graph, graph.start_node_id, db)

    def continue_after_approval(
        self,
        instance: ApprovalInstance,
        graph: VersionGraph,
        execution: ApprovalNodeExecution,
        db: Session,
    ) -> None:
        """人工审批节点形成通过结果后，完成节点记录并继续推进。

        审批动作已经写入不可变记录，此时不能再回滚整个事务。推进过程中发生异常
        时把实例置为 ERROR，保留审批痕迹并让后台能够发现这条异常实例。
        """

        now = utc_now()
        # 节点已经形成结果，其余待办任务不再需要处理。
        self.repository.cancel_pending_tasks_by_node(execution.id, now, db)
        execution.result_json = {
            **execution.result_json,
            "outcome": OUTCOME_APPROVED,
        }

        next_node_id = self.complete_node(instance, graph, execution, db)
        if next_node_id is None:
            self.fail_instance(instance, execution, "当前节点没有可走的后续连线", db)
            return

        try:
            self._run(instance, graph, next_node_id, db)
        except ProcessStateError as exc:
            self.fail_instance(instance, None, str(exc), db)

    def reject_approval_node(
        self,
        instance: ApprovalInstance,
        execution: ApprovalNodeExecution,
        db: Session,
    ) -> None:
        """人工审批节点被拒绝时立即拒绝整个审批实例。

        AND 和 OR 两种模式下任意一人拒绝都立即拒绝实例，其余待处理任务同时取消。
        """

        now = utc_now()
        self.repository.cancel_pending_tasks_by_node(execution.id, now, db)

        execution.status = NODE_EXECUTION_STATUS_REJECTED
        execution.completed_at = now
        execution.updated_at = now
        execution.result_json = {
            **execution.result_json,
            "outcome": OUTCOME_REJECTED,
        }
        self.repository.add_node_execution(execution, db)

        instance.status = INSTANCE_STATUS_REJECTED
        instance.finished_at = now
        instance.current_node_execution_id = None
        instance.updated_at = now
        self.repository.add_instance(instance, db)

    def complete_node(
        self,
        instance: ApprovalInstance,
        graph: VersionGraph,
        execution: ApprovalNodeExecution,
        db: Session,
    ) -> UUID | None:
        """完成节点执行记录并按条件选择后续节点，没有可走路径时返回 None。"""

        connection = select_next_connection(
            graph.outgoing(execution.node_id),
            instance.approval_form_json or {},
            graph.field_formats,
        )
        now = utc_now()
        execution.status = NODE_EXECUTION_STATUS_COMPLETED
        execution.completed_at = now
        execution.updated_at = now

        if connection is None:
            self.repository.add_node_execution(execution, db)
            return None

        # 记录实际命中的连线和是否走了条件分支，供时间线展示。
        execution.next_node_id = connection.target_node_id
        execution.result_json = {
            **execution.result_json,
            "next_node_id": str(connection.target_node_id),
            "connection_index": connection.order_index,
            "condition_hit": connection.condition is not None,
        }
        self.repository.add_node_execution(execution, db)
        return connection.target_node_id

    def finish_instance(
        self,
        instance: ApprovalInstance,
        execution: ApprovalNodeExecution,
        db: Session,
    ) -> None:
        """走完结束节点：实例置为"审批通过"并留下执行记录。

        这是实例以通过结束的唯一汇合点：人工审批推进和 START → END 直接结束都会
        经过这里，因此业务执行记录只能挂在本方法，不能挂在任务服务上。审批被拒绝
        走 ``reject_instance``，不产生业务执行任务。

        通过时由同模块的业务执行服务写入 PENDING 执行记录，但只写当前 Session，
        不提交事务，也不发送任何外部 HTTP 请求。
        """

        now = utc_now()
        execution.status = NODE_EXECUTION_STATUS_COMPLETED
        execution.completed_at = now
        execution.updated_at = now
        execution.result_json = {
            **execution.result_json,
            "result_status": INSTANCE_STATUS_APPROVED,
        }
        self.repository.add_node_execution(execution, db)

        instance.status = INSTANCE_STATUS_APPROVED
        instance.finished_at = now
        instance.current_node_execution_id = None
        instance.updated_at = now
        self.repository.add_instance(instance, db)

        # 记录创建与实例状态更新同事务：写入失败时审批也会一起回滚，避免出现审批
        # 已经通过却没有执行任务的状态。
        self.business_execution_service.create_execution_record(instance, db)

    def fail_instance(
        self,
        instance: ApprovalInstance,
        execution: ApprovalNodeExecution | None,
        message: str,
        db: Session,
    ) -> None:
        """推进失败时把实例置为 ERROR，并取消尚未处理的待办任务。"""

        now = utc_now()
        failed_execution = execution
        if failed_execution is None:
            failed_execution = self.repository.get_active_node_execution(instance.id, db)
        if failed_execution is not None:
            failed_execution.status = NODE_EXECUTION_STATUS_ERROR
            failed_execution.completed_at = now
            failed_execution.updated_at = now
            failed_execution.result_json = {
                **failed_execution.result_json,
                "error": message,
            }
            self.repository.add_node_execution(failed_execution, db)

        self.repository.cancel_pending_tasks_by_instance(instance.id, now, db)

        instance.status = INSTANCE_STATUS_ERROR
        instance.finished_at = now
        instance.current_node_execution_id = None
        instance.updated_at = now
        self.repository.add_instance(instance, db)

    # ------------------------------------------------------------------
    # 审批人与任务
    # ------------------------------------------------------------------

    def resolve_approver_person_ids(
        self,
        node: ApprovalProcessVersionNode,
    ) -> list[UUID]:
        """读取版本节点配置中的审批人，保持配置顺序并去重。"""

        raw_approvers = node.config_json.get("approvers")
        if not isinstance(raw_approvers, Sequence) or isinstance(raw_approvers, str):
            return []

        person_ids: list[UUID] = []
        seen_person_ids: set[UUID] = set()
        for raw_approver in raw_approvers:
            if not isinstance(raw_approver, Mapping):
                continue
            try:
                person_id = UUID(str(raw_approver.get("person_id")))
            except (TypeError, ValueError):
                continue
            if person_id in seen_person_ids:
                continue
            seen_person_ids.add(person_id)
            person_ids.append(person_id)
        return person_ids

    def create_approval_tasks(
        self,
        instance: ApprovalInstance,
        execution: ApprovalNodeExecution,
        approver_person_ids: Sequence[UUID],
        db: Session,
    ) -> list[ApprovalTask]:
        """为全部审批人同时创建待办任务。"""

        snapshots = self.load_person_snapshots(approver_person_ids, db)
        tasks = [
            ApprovalTask(
                instance_id=instance.id,
                node_execution_id=execution.id,
                approver_person_id=person_id,
                approver_snapshot_json=snapshots.get(
                    person_id,
                    {"person_id": str(person_id)},
                ),
                status=TASK_STATUS_PENDING,
            )
            for person_id in approver_person_ids
        ]
        self.repository.add_tasks(tasks, db)
        return tasks

    def load_person_snapshots(
        self,
        person_ids: Sequence[UUID],
        db: Session,
    ) -> dict[UUID, dict]:
        """批量读取人员展示信息，供发起人和审批人快照使用。

        人员已经不存在时返回空字典，调用方仍会保存人员 ID，审批流程不因为主数据
        缺失而中断。
        """

        unique_person_ids = list(dict.fromkeys(person_ids))
        if not unique_person_ids:
            return {}

        persons = self.organization_service.list_persons_by_ids(unique_person_ids, db)
        return {
            person.id: {"person_id": str(person.id), "name": person.name}
            for person in persons
        }

    # ------------------------------------------------------------------
    # 内部推进
    # ------------------------------------------------------------------

    def _run(
        self,
        instance: ApprovalInstance,
        graph: VersionGraph,
        node_id: UUID,
        db: Session,
    ) -> None:
        """从指定节点开始逐个进入节点，直到需要等待人工处理或实例结束。

        已发布版本禁止成环，因此每个节点最多进入一次。这里仍然保留步数上限，避免
        编排数据被写坏时把请求拖进死循环。
        """

        current_node_id = node_id

        for _ in range(MAX_ADVANCE_STEPS):
            node = graph.get_node(current_node_id)
            if node is None:
                raise ProcessStateError("流程版本中不存在待进入的节点，无法推进审批")

            handler = NODE_HANDLERS.get(node.node_type)
            if handler is None:
                raise ProcessStateError(
                    f"节点类型 {node.node_type} 没有对应的执行器，无法推进审批"
                )

            execution = self._enter_node(instance, graph, node, db)
            next_node_id = handler.handle(
                NodeContext(
                    engine=self,
                    instance=instance,
                    graph=graph,
                    execution=execution,
                    node=node,
                    db=db,
                )
            )
            if next_node_id is None:
                return
            current_node_id = next_node_id

        raise ProcessStateError("流程推进步数超过上限，请检查流程编排是否成环")

    def _enter_node(
        self,
        instance: ApprovalInstance,
        graph: VersionGraph,
        node: ApprovalProcessVersionNode,
        db: Session,
    ) -> ApprovalNodeExecution:
        """进入节点并创建活动节点执行记录。"""

        now = utc_now()
        execution = ApprovalNodeExecution(
            instance_id=instance.id,
            process_version_id=graph.version.id,
            node_id=node.id,
            node_type=node.node_type,
            node_name=node.name,
            sequence_no=self.repository.get_max_sequence_no(instance.id, db) + 1,
            status=NODE_EXECUTION_STATUS_ACTIVE,
            entered_at=now,
            result_json={},
        )
        self.repository.add_node_execution(execution, db)
        # 先落库节点执行记录，实例才能安全地指向它。
        db.flush()

        instance.current_node_execution_id = execution.id
        instance.updated_at = now
        self.repository.add_instance(instance, db)
        return execution
