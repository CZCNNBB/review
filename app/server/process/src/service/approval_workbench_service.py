"""管理台统一工作台的审批与抄送任务查询。"""

from dataclasses import dataclass

from sqlmodel import Session

from app.server.process.src.models.approval_model import (
    ApprovalInstance,
    ApprovalNodeExecution,
    ApprovalTask,
)
from app.server.process.src.repository.approval_repository import ApprovalRepository


@dataclass(frozen=True)
class WorkItem:
    """统一任务及其审批单、节点展示信息。"""

    task: ApprovalTask
    instance: ApprovalInstance
    execution: ApprovalNodeExecution


class ApprovalWorkbenchService:
    """批量装配工作台需要的审批和抄送任务。"""

    def __init__(self, repository: ApprovalRepository | None = None):
        """初始化仓储，并允许单元测试注入替身。"""

        self.repository = repository or ApprovalRepository()

    def list_items(
        self,
        db: Session,
        offset: int = 0,
        limit: int = 500,
    ) -> list[WorkItem]:
        """分页查询统一任务表，并批量读取实例和节点避免逐条访问数据库。"""

        tasks = self.repository.list_work_items(db, offset, limit)
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
