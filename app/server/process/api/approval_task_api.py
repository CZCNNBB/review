"""审批任务的统一处理接口。

接入可信登录身份前，管理密钥校验调用者，person_id 核对任务确实分配给该人员。
接入项目平台登录身份后改为从依赖注入读取当前人员。
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.common.schemas.result import Result
from app.common.security import verify_admin_key
from app.server.process.api.process_api import raise_process_http_error
from app.server.process.src.schemas.approval_schema import (
    ApprovalActionResponse,
    ApprovalTaskDecisionRequest,
)
from app.server.process.src.service.approval_task_service import (
    ApprovalTaskService,
    TaskActionView,
)
from app.server.process.src.service.exceptions import (
    ApprovalNotFoundError,
    ApprovalPermissionError,
    ApprovalStateError,
    ProcessStateError,
)


router = APIRouter()
approval_task_service = ApprovalTaskService()


def build_action_response(view: TaskActionView) -> ApprovalActionResponse:
    """把审批操作结果转换成响应。"""

    current_node_execution = view.current_node_execution
    return ApprovalActionResponse(
        instance_id=view.instance.id,
        instance_status=view.instance.status,
        task_id=view.task.id,
        task_status=view.task.status,
        node_execution_id=view.node_execution.id,
        node_execution_status=view.node_execution.status,
        current_node_name=(
            current_node_execution.node_name if current_node_execution else None
        ),
        idempotent_replay=view.idempotent_replay,
    )


@router.post(
    "/approval-tasks/{task_id}/decisions",
    response_model=Result[ApprovalActionResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="处理审批任务",
)
def decide_approval_task(
    task_id: UUID,
    request: ApprovalTaskDecisionRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[ApprovalActionResponse]:
    """按请求中的 action 同意或拒绝任务，并推进审批实例。"""

    try:
        view = approval_task_service.handle_task(task_id, request.action, request, db)
        return Result.success(build_action_response(view))
    except (
        ApprovalNotFoundError,
        ApprovalPermissionError,
        ApprovalStateError,
        ProcessStateError,
    ) as exc:
        raise_process_http_error(exc)
