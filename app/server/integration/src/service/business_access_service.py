"""业务接入应用服务：租户作用域校验、业务动作校验和审批发起事务协调。

本模块是发起审批的最外层应用服务，负责把审批实例、首批审批任务和租户使用记录放在
同一个数据库事务中提交。process 和 integration 的业务 Service 都不直接查询租户
绑定表，租户能力统一通过 TenantScope 接口调用。
"""

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.server.integration.src.service.business_action_service import (
    BusinessActionService,
)
from app.server.integration.src.service.exceptions import BusinessActionStateError
from app.server.process.src.schemas.approval_schema import ApprovalStartRequest
from app.server.process.src.service.approval_instance_service import (
    ApprovalInstanceService,
    StartedInstance,
)
from app.server.process.src.service.exceptions import ApprovalConflictError
from app.server.tenant.src.scope.business_access import BusinessAccessContext


class BusinessAccessService:
    """协调租户授权、业务动作规则和审批实例创建。"""

    def __init__(
        self,
        approval_instance_service: ApprovalInstanceService | None = None,
        business_action_service: BusinessActionService | None = None,
    ):
        """初始化业务接入服务并允许测试注入依赖。"""

        self.approval_instance_service = (
            approval_instance_service or ApprovalInstanceService()
        )
        self.business_action_service = business_action_service or BusinessActionService()

    def start_approval(
        self,
        process_id: UUID,
        request: ApprovalStartRequest,
        context: BusinessAccessContext,
        db: Session,
    ) -> StartedInstance:
        """在单个事务中完成租户校验、业务校验、审批发起和使用记录写入。

        处理顺序固定为：流程授权、业务动作授权、执行参数校验、创建并推进审批实例、
        写入租户使用记录、提交事务。任何一步失败都整体回滚，因此不会出现已经提交却
        找不到租户归属的孤立审批实例。
        """

        # 租户模式下确认租户可以使用该审批流，全局模式下直接放行。
        context.process_scope.require_access(process_id, db)

        if request.action_code:
            # 业务执行必须通过租户使用记录确定回调地址和 Service Token，全局模式下没有
            # 租户归属，审批通过后无法执行。这里在发起阶段直接拒绝，不让申请进入一条
            # 注定失败的链路。
            if context.tenant_id is None:
                raise BusinessActionStateError(
                    "当前运行在全局模式，不能使用 action_code："
                    "审批通过后没有可用的租户回调配置"
                )

            business_action = self.business_action_service.resolve_tenant_action(
                request.action_code,
                context.action_scope,
                db,
            )
            self.business_action_service.validate_execution_payload(
                business_action,
                request.execution_payload,
            )

        started = self.approval_instance_service.create_and_start_instance(
            process_id=process_id,
            request=request,
            db=db,
            tenant_id=context.tenant_id,
        )
        if started.idempotent_replay:
            # 重复发起不创建新实例，也不重复写入使用记录。
            return started

        self._write_usage_record(started, context, db)

        try:
            # 审批实例、首批节点执行、首批任务和租户使用记录必须原子提交。
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            # 并发发起同一业务单据时由数据库唯一约束决出胜负，失败的一方读取并返回
            # 获胜请求已经提交的审批实例，而不是留下半成品数据。
            replayed = self.approval_instance_service.resolve_idempotent_instance(
                process_id=process_id,
                request=request,
                db=db,
                tenant_id=context.tenant_id,
            )
            if replayed is None:
                raise ApprovalConflictError("审批发起冲突，请重试") from exc
            return replayed

        return started

    @staticmethod
    def _write_usage_record(
        started: StartedInstance,
        context: BusinessAccessContext,
        db: Session,
    ) -> None:
        """在当前事务中写入租户使用记录。

        使用记录只保存租户归属和关联信息，审批状态、当前节点和耗时仍然从 process
        运行表读取，避免同一份状态出现两份不一致的副本。
        """

        instance = started.instance
        context.instance_scope.bind(
            instance.id,
            db,
            attributes={
                "process_id": instance.process_id,
                "process_version_id": instance.process_version_id,
                "business_key": instance.business_key,
                "action_code": instance.action_code,
            },
        )
