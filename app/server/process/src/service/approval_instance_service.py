"""审批实例发起、详情和时间线业务逻辑。"""

from dataclasses import dataclass
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
    ) -> StartedInstance:
        """按流程当前已发布版本创建审批实例并推进到首个等待节点。

        业务系统只传 process_id，版本在发起时确定并与实例绑定，之后发布新版本不会
        影响本次审批。相同幂等键且请求内容一致的重复请求返回原审批实例，内容变化
        时返回冲突，避免新的审批数据被静默忽略。
        """

        idempotency_key = build_idempotency_key(
            process_id=process_id,
            business_key=request.business_key,
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
            # 实例、首条节点执行记录和首批审批任务必须在同一个事务中提交。
            self.engine.start_instance(instance, graph, db)
            db.commit()
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

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

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
