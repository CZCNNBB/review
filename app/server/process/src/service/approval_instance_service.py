"""审批实例发起、详情和时间线业务逻辑。"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.server.organization.src.service.organization_service import OrganizationService
from app.server.process.src.constants import (
    INSTANCE_STATUS_RUNNING,
    PROCESS_STATUS_ENABLED,
    PROCESS_VERSION_STATUS_PUBLISHED,
    RULE_APPLICANT_INVALID,
    RULE_APPROVAL_FORM_INVALID,
    TASK_STATUS_PENDING,
)
from app.server.process.src.engine.graph import build_version_graph
from app.server.process.src.engine.runner import ApprovalEngine
from app.server.process.src.models.approval_model import (
    ApprovalInstance,
    ApprovalNodeExecution,
    ApprovalRecord,
    ApprovalTask,
)
from app.server.process.src.models.process_model import (
    ApprovalProcess,
    ApprovalProcessVersion,
)
from app.server.process.src.repository.approval_repository import ApprovalRepository
from app.server.process.src.repository.process_repository import ProcessRepository
from app.server.process.src.schemas.approval_schema import ApprovalStartRequest
from app.server.process.src.service.exceptions import (
    ApprovalConflictError,
    ApprovalNotFoundError,
    ProcessNotFoundError,
    ProcessStateError,
    ProcessValidationError,
)
from app.server.process.src.service.process_validation import ValidationIssue
from app.server.process.src.utils.idempotency import (
    build_idempotency_key,
    build_request_digest,
)
from app.server.process.src.utils.json_schema import validate_instance


@dataclass(frozen=True)
class StartedInstance:
    """发起审批后的实例状态。"""

    instance: ApprovalInstance
    version: ApprovalProcessVersion
    current_node_execution: ApprovalNodeExecution | None
    pending_approver_person_ids: tuple[UUID, ...]
    idempotent_replay: bool


@dataclass(frozen=True)
class InstanceDetailView:
    """审批详情和时间线共用的完整运行数据。"""

    instance: ApprovalInstance
    process: ApprovalProcess
    version: ApprovalProcessVersion
    node_executions: tuple[ApprovalNodeExecution, ...]
    tasks: tuple[ApprovalTask, ...]
    records: tuple[ApprovalRecord, ...]


@dataclass(frozen=True)
class InstanceOverview:
    """审批实例的运行摘要，供租户使用记录列表组装展示信息。

    这些字段统一从 process 运行表读取，不在 tenant.process_usage_record 中重复保存。
    """

    instance_id: UUID
    status: str
    title: str
    current_node_name: str | None
    started_at: datetime | None
    finished_at: datetime | None


class ApprovalInstanceService:
    """提供发起审批、审批详情和运行时间线查询能力。"""

    def __init__(
        self,
        repository: ApprovalRepository | None = None,
        process_repository: ProcessRepository | None = None,
        organization_service: OrganizationService | None = None,
        engine: ApprovalEngine | None = None,
    ):
        """初始化审批实例服务并允许测试注入依赖。"""

        self.repository = repository or ApprovalRepository()
        self.process_repository = process_repository or ProcessRepository()
        self.organization_service = organization_service or OrganizationService()
        self.engine = engine or ApprovalEngine(
            repository=self.repository,
            organization_service=self.organization_service,
        )

    # ------------------------------------------------------------------
    # 发起审批
    # ------------------------------------------------------------------

    def start_instance(
        self,
        process_id: UUID,
        request: ApprovalStartRequest,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> StartedInstance:
        """创建并推进审批实例，然后提交本次事务。

        适用于不需要把审批实例和其他模块数据放在同一事务里的调用方。业务接入接口
        需要把租户使用记录和审批实例原子提交，改用 create_and_start_instance 后由
        最外层应用服务统一提交。
        """

        started = self.create_and_start_instance(
            process_id=process_id,
            request=request,
            db=db,
            tenant_id=tenant_id,
        )
        db.commit()
        return started

    def create_and_start_instance(
        self,
        process_id: UUID,
        request: ApprovalStartRequest,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> StartedInstance:
        """按流程当前已发布版本创建审批实例并推进到首个等待节点，但不提交事务。

        业务系统只传 process_id，版本在发起时确定并与实例绑定，之后发布新版本不会
        影响本次审批。相同幂等键且请求内容一致的重复请求返回原审批实例，内容变化
        时返回冲突，避免新的审批数据被静默忽略。

        方法内只执行添加、flush 和流程推进，调用方必须在同一事务中补齐其他模块的
        数据后再提交，否则会产生无法按租户查询的孤立审批实例。
        """

        idempotency_key = build_idempotency_key(
            process_id=process_id,
            business_key=request.business_key,
            tenant_id=tenant_id,
        )
        request_digest = build_request_digest(self._build_request_payload(request))

        existing_instance = self.repository.get_instance_by_idempotency_key(
            idempotency_key,
            db,
        )
        if existing_instance is not None:
            self._ensure_same_request(existing_instance, request_digest)
            return self._build_started(existing_instance, db, idempotent_replay=True)

        process = self.process_repository.get_process_for_update(process_id, db)
        if process is None:
            raise ProcessNotFoundError("审批流不存在")
        if process.status != PROCESS_STATUS_ENABLED:
            raise ProcessStateError("审批流尚未发布或已停用，不能发起审批")
        if process.current_version_id is None:
            raise ProcessStateError("审批流没有已发布版本，不能发起审批")

        version = self.process_repository.get_version_by_id(
            process.current_version_id,
            db,
        )
        if version is None or version.status != PROCESS_VERSION_STATUS_PUBLISHED:
            raise ProcessStateError("审批流当前版本不可用，不能发起审批")

        self._validate_approval_form(request.approval_form, version)
        applicant_snapshot = self._validate_applicant(request.applicant_person_id, db)

        # 版本节点在流程行锁内读取，保证本次实例使用同一份完整的已发布版本。
        graph = build_version_graph(
            version,
            self.process_repository.list_nodes(version.id, db),
        )

        instance = ApprovalInstance(
            process_id=process.id,
            process_version_id=version.id,
            business_key=request.business_key,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            title=request.title,
            applicant_person_id=request.applicant_person_id,
            applicant_snapshot_json=applicant_snapshot,
            approval_form_json=dict(request.approval_form),
            execution_payload_json=dict(request.execution_payload),
            action_code=request.action_code,
            status=INSTANCE_STATUS_RUNNING,
        )
        self.repository.add_instance(instance, db)

        try:
            # 实例、首条节点执行记录和首批审批任务在同一个事务中写入，此处只 flush。
            self.engine.start_instance(instance, graph, db)
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            # 并发提交相同幂等键时由唯一约束决出胜负，失败的一方返回已有实例。
            conflicted_instance = self.repository.get_instance_by_idempotency_key(
                idempotency_key,
                db,
            )
            if conflicted_instance is not None:
                self._ensure_same_request(conflicted_instance, request_digest)
                return self._build_started(
                    conflicted_instance,
                    db,
                    idempotent_replay=True,
                )
            raise ApprovalConflictError("审批实例创建冲突，请重试") from exc
        except Exception:
            db.rollback()
            raise

        db.refresh(instance)
        return self._build_started(instance, db, idempotent_replay=False)

    def resolve_idempotent_instance(
        self,
        process_id: UUID,
        request: ApprovalStartRequest,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> StartedInstance | None:
        """按幂等键读取已经存在的审批实例，供并发冲突后返回幂等重放结果。

        调用方在租户使用记录写入冲突并回滚后调用本方法：此时获胜的请求已经提交了
        实例和使用记录，这里重新读取并比对请求摘要。内容不一致时仍然返回 409。
        """

        idempotency_key = build_idempotency_key(
            process_id=process_id,
            business_key=request.business_key,
            tenant_id=tenant_id,
        )
        existing_instance = self.repository.get_instance_by_idempotency_key(
            idempotency_key,
            db,
        )
        if existing_instance is None:
            return None

        request_digest = build_request_digest(self._build_request_payload(request))
        self._ensure_same_request(existing_instance, request_digest)
        return self._build_started(existing_instance, db, idempotent_replay=True)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_instance_overviews(
        self,
        instance_ids: list[UUID],
        db: Session,
    ) -> dict[UUID, InstanceOverview]:
        """批量读取审批实例运行摘要，供租户使用记录列表组装展示信息。

        运行状态只从 process 运行表读取，不在租户使用记录中重复保存，避免同一份
        状态出现两份不一致的副本。
        """

        unique_instance_ids = list(dict.fromkeys(instance_ids))
        if not unique_instance_ids:
            return {}

        instances = self.repository.list_instances_by_ids(unique_instance_ids, db)

        # 一次性读取全部当前节点执行记录，避免逐条实例查询节点名称。
        current_execution_ids = [
            instance.current_node_execution_id
            for instance in instances
            if instance.current_node_execution_id is not None
        ]
        executions = self.repository.list_node_executions_by_ids(
            current_execution_ids,
            db,
        )
        node_name_by_execution_id = {
            execution.id: execution.node_name for execution in executions
        }

        overviews: dict[UUID, InstanceOverview] = {}
        for instance in instances:
            current_node_name = None
            if instance.current_node_execution_id is not None:
                current_node_name = node_name_by_execution_id.get(
                    instance.current_node_execution_id
                )
            overviews[instance.id] = InstanceOverview(
                instance_id=instance.id,
                status=instance.status,
                title=instance.title,
                current_node_name=current_node_name,
                started_at=instance.started_at,
                finished_at=instance.finished_at,
            )
        return overviews

    def get_instance_view(self, instance_id: UUID, db: Session) -> InstanceDetailView:
        """读取审批实例的完整运行数据，供详情和时间线接口使用。"""

        instance = self.repository.get_instance_by_id(instance_id, db)
        if instance is None:
            raise ApprovalNotFoundError("审批实例不存在")

        process = self.process_repository.get_process_by_id(instance.process_id, db)
        if process is None:
            raise ApprovalNotFoundError("审批实例关联的审批流不存在")

        version = self.process_repository.get_version_by_id(
            instance.process_version_id,
            db,
        )
        if version is None:
            raise ApprovalNotFoundError("审批实例关联的流程版本不存在")

        return InstanceDetailView(
            instance=instance,
            process=process,
            version=version,
            node_executions=tuple(
                self.repository.list_node_executions(instance.id, db)
            ),
            tasks=tuple(self.repository.list_tasks_by_instance(instance.id, db)),
            records=tuple(self.repository.list_records_by_instance(instance.id, db)),
        )

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _build_started(
        self,
        instance: ApprovalInstance,
        db: Session,
        idempotent_replay: bool,
    ) -> StartedInstance:
        """组装发起审批的返回结果，包含当前节点和仍在等待的审批人。"""

        version = self.process_repository.get_version_by_id(
            instance.process_version_id,
            db,
        )
        if version is None:
            raise ProcessStateError("审批实例绑定的流程版本不存在")

        current_node_execution = None
        if instance.current_node_execution_id is not None:
            current_node_execution = self.repository.get_node_execution_by_id(
                instance.current_node_execution_id,
                db,
            )

        pending_person_ids = tuple(
            task.approver_person_id
            for task in self.repository.list_tasks_by_instance(instance.id, db)
            if task.status == TASK_STATUS_PENDING
        )

        return StartedInstance(
            instance=instance,
            version=version,
            current_node_execution=current_node_execution,
            pending_approver_person_ids=pending_person_ids,
            idempotent_replay=idempotent_replay,
        )

    @staticmethod
    def _build_request_payload(request: ApprovalStartRequest) -> dict:
        """提取参与请求摘要比对的字段。

        审批单数据和业务执行参数是必须一致的核心内容，标题和发起人变化同样说明这是
        另一次申请，一并纳入比对。
        """

        return {
            "business_key": request.business_key,
            "title": request.title,
            "applicant_person_id": (
                str(request.applicant_person_id)
                if request.applicant_person_id is not None
                else None
            ),
            "action_code": request.action_code,
            "approval_form": request.approval_form,
            "execution_payload": request.execution_payload,
        }

    @staticmethod
    def _ensure_same_request(
        instance: ApprovalInstance,
        request_digest: str,
    ) -> None:
        """重放时确认请求内容没有变化。"""

        # 早期创建的实例没有保存摘要，无法比对，保持返回已有实例的行为。
        if instance.request_digest is None:
            return
        if instance.request_digest != request_digest:
            raise ApprovalConflictError(
                "该业务单据已经发起过审批，本次请求内容与已发起的审批不一致；"
                "如需提交新内容，请使用新的业务单据标识"
            )

    @staticmethod
    def _validate_approval_form(
        approval_form: dict,
        version: ApprovalProcessVersion,
    ) -> None:
        """按版本冻结的表单 Schema 校验审批单数据。"""

        form_schema = version.form_schema_json
        if not isinstance(form_schema, dict) or not form_schema:
            return

        form_issues = validate_instance(
            approval_form,
            form_schema,
            root_path="approval_form",
        )
        if not form_issues:
            return

        raise ProcessValidationError(
            "审批单数据校验未通过",
            [
                ValidationIssue(
                    code=RULE_APPROVAL_FORM_INVALID,
                    message=issue.message,
                    field=issue.path,
                )
                for issue in form_issues
            ],
        )

    def _validate_applicant(
        self,
        applicant_person_id: UUID | None,
        db: Session,
    ) -> dict:
        """校验发起人存在且启用，并返回发起时的人员展示快照。"""

        if applicant_person_id is None:
            return {}

        persons = self.organization_service.list_persons_by_ids(
            [applicant_person_id],
            db,
        )
        if not persons:
            raise ProcessValidationError(
                "发起人不存在",
                [
                    ValidationIssue(
                        code=RULE_APPLICANT_INVALID,
                        message="发起人不存在",
                        field="applicant_person_id",
                    )
                ],
            )

        person = persons[0]
        if person.status != "ENABLED":
            raise ProcessValidationError(
                "发起人已停用，不能发起审批",
                [
                    ValidationIssue(
                        code=RULE_APPLICANT_INVALID,
                        message="发起人已停用，不能发起审批",
                        field="applicant_person_id",
                    )
                ],
            )

        return {"person_id": str(person.id), "name": person.name}
