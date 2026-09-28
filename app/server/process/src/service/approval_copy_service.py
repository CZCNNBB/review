"""审批单抄送收件箱的查询和收件人校验。"""

from dataclasses import dataclass
from uuid import UUID

from sqlmodel import Session

from app.server.process.src.models.approval_model import (
    ApprovalTask,
    ApprovalInstance,
    ApprovalNodeExecution,
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
class CopyListItem:
    """一条抄送记录及其审批单、节点展示信息。"""

    copy: ApprovalTask
    instance: ApprovalInstance
    execution: ApprovalNodeExecution


class ApprovalCopyService:
    """提供按收件人查询和只读打开抄送审批单的能力。"""

    def __init__(
        self,
        repository: ApprovalRepository | None = None,
        instance_service: ApprovalInstanceService | None = None,
    ):
        """初始化抄送服务并允许测试注入依赖。"""

        self.repository = repository or ApprovalRepository()
        self.instance_service = instance_service or ApprovalInstanceService(
            repository=self.repository
        )

    def list_person_copies(
        self,
        person_id: UUID | None,
        db: Session,
        offset: int = 0,
        limit: int = 100,
    ) -> list[CopyListItem]:
        """分页查询抄送记录；人员为空时汇总全部收件人的记录。"""

        copies = self.repository.list_person_copies(person_id, db, offset, limit)
        if not copies:
            return []

        instances = self.repository.list_instances_by_ids(
            list({copy.instance_id for copy in copies}), db
        )
        executions = self.repository.list_node_executions_by_ids(
            list({copy.node_execution_id for copy in copies}), db
        )
        instance_by_id = {instance.id: instance for instance in instances}
        execution_by_id = {execution.id: execution for execution in executions}

        items: list[CopyListItem] = []
        for copy in copies:
            instance = instance_by_id.get(copy.instance_id)
            execution = execution_by_id.get(copy.node_execution_id)
            if instance is None or execution is None:
                # 外键正常时不会发生；损坏数据不应让整页收件箱不可用。
                continue
            items.append(CopyListItem(copy, instance, execution))
        return items

    def get_recipient_instance_view(
        self,
        copy_id: UUID,
        person_id: UUID,
        db: Session,
    ) -> InstanceDetailView:
        """确认抄送归属后，返回审批单只读详情。"""

        copy = self.repository.get_copy_by_id(copy_id, db)
        if copy is None:
            raise ApprovalNotFoundError("抄送记录不存在")
        if copy.recipient_person_id != person_id:
            raise ApprovalPermissionError("该审批单没有抄送给当前人员")
        return self.instance_service.get_instance_view(copy.instance_id, db)
