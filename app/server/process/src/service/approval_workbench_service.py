"""管理台统一工作台的审批与抄送任务查询。"""

from dataclasses import dataclass
from uuid import UUID

from sqlmodel import Session

from app.server.process.src.models.approval_model import (
    ApprovalInstance,
    ApprovalNodeExecution,
    ApprovalTask,
)
from app.server.process.src.repository.approval_repository import ApprovalRepository
from app.server.process.src.service.approval_instance_service import (
    ApprovalInstanceService,
    InstanceDetailView,
)
from app.server.process.src.service.exceptions import (
    ApprovalNotFoundError,
    ApprovalPermissionError,
)


@dataclass(frozen=True)
class WorkItem:
    """统一任务及其审批单、节点展示信息。"""

    task: ApprovalTask
    instance: ApprovalInstance
    execution: ApprovalNodeExecution


class ApprovalWorkbenchService:
    """批量装配工作台需要的审批和抄送任务。"""

    def __init__(
        self,
        repository: ApprovalRepository | None = None,
        instance_service: ApprovalInstanceService | None = None,
    ):
        """初始化任务仓储和实例服务，并允许测试注入依赖。"""

        self.repository = repository or ApprovalRepository()
        self.instance_service = instance_service or ApprovalInstanceService(
            repository=self.repository
        )

    def get_recipient_instance_view(
        self,
        task_id: UUID,
        person_id: UUID,
        db: Session,
    ) -> InstanceDetailView:
        """校验任务接收人后，读取审批或抄送任务对应的审批单。"""

        task = self.repository.get_task_by_id(task_id, db)
        if task is None:
            raise ApprovalNotFoundError("任务不存在")
        if task.recipient_person_id != person_id:
            raise ApprovalPermissionError("任务不属于当前人员")
        return self.instance_service.get_instance_view(task.instance_id, db)

    def list_items(
        self,
        db: Session,
        person_id: UUID | None = None,
        task_type: str | None = None,
        statuses: list[str] | None = None,
        offset: int = 0,
        limit: int = 500,
    ) -> list[WorkItem]:
        """按人员、类型和状态查询，再批量装配实例与节点展示信息。"""

        tasks = self.repository.list_work_items(
            db,
            person_id=person_id,
            task_type=task_type,
            statuses=statuses,
            offset=offset,
            limit=limit,
        )
        if not tasks:
            return []

        instances = self.repository.list_instances_by_ids(
            list({task.instance_id for task in tasks}), db
        )
        executions = self.repository.list_node_executions_by_ids(
            list({task.node_execution_id for task in tasks}), db
        )
        instance_by_id = {instance.id: instance for instance in instances}
        execution_by_id = {execution.id: execution for execution in executions}

        items: list[WorkItem] = []
        for task in tasks:
            instance = instance_by_id.get(task.instance_id)
            execution = execution_by_id.get(task.node_execution_id)
            if instance is None or execution is None:
                # 外键正常时不会发生；个别损坏记录不应让整页工作台不可用。
                continue
            items.append(WorkItem(task, instance, execution))
        return items
