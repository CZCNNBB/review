"""审批任务待办、已办和审批操作接口。

接入可信登录身份前，任务查询和审批操作显式传递 person_id，接口层校验任务确实
分配给了该人员。接入项目平台登录身份后改为从依赖注入读取当前人员。
"""

from enum import Enum
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.common.schemas.result import Result
from app.server.process.api.approval_view_builder import build_task_response
from app.server.process.api.process_api import raise_process_http_error
from app.server.process.src.constants import (
    RECORD_ACTION_APPROVE,
    RECORD_ACTION_REJECT,
    TASK_STATUS_APPROVED,
    TASK_STATUS_CANCELLED,
    TASK_STATUS_PENDING,
    TASK_STATUS_REJECTED,
)
from app.server.process.src.schemas.approval_schema import (
    ApprovalActionResponse,
    ApprovalTaskActionRequest,
    ApprovalTaskResponse,
)
from app.server.process.src.service.approval_task_service import (
    ApprovalTaskService,
    TaskActionView,
    TaskListItem,
)
from app.server.process.src.service.exceptions import (
    ApprovalNotFoundError,
    ApprovalPermissionError,
    ApprovalStateError,
    ProcessStateError,
)


class TaskStatusFilter(str, Enum):
    """任务列表支持的状态筛选值，取值与运行表状态保持一致。"""

    PENDING = TASK_STATUS_PENDING
    APPROVED = TASK_STATUS_APPROVED
    REJECTED = TASK_STATUS_REJECTED
    CANCELLED = TASK_STATUS_CANCELLED


router = APIRouter()
approval_task_service = ApprovalTaskService()


def build_task_list_response(item: TaskListItem) -> ApprovalTaskResponse:
    """把待办或已办条目转换成响应。"""

    return build_task_response(
        item.task,
        instance_title=item.instance_title,
        business_key=item.business_key,
        node_name=item.node_name,
    )


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


@router.get(
    "/approval-tasks",
    response_model=Result[list[ApprovalTaskResponse]],
    summary="查询人员待办或已办任务",
)
def list_approval_tasks(
    person_id: UUID = Query(description="审批人 ID"),
    status: list[TaskStatusFilter] | None = Query(
        default=None,
        description="任务状态，可重复传递；不传表示不限状态",
    ),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_postgres_engine),
) -> Result[list[ApprovalTaskResponse]]:
    """按人员查询待办或已办任务，按任务产生时间倒序返回。"""

    try:
        items = approval_task_service.list_person_tasks(
            person_id,
            [item.value for item in status] if status else [],
            db,
            offset=offset,
            limit=limit,
        )
        return Result.success([build_task_list_response(item) for item in items])
    except ProcessStateError as exc:
        raise_process_http_error(exc)


@router.post(
    "/approval-tasks/{task_id}/approve",
    response_model=Result[ApprovalActionResponse],
    summary="同意审批任务",
)
def approve_approval_task(
    task_id: UUID,
    request: ApprovalTaskActionRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[ApprovalActionResponse]:
    """同意分配给当前人员的待办任务，并按 AND、OR 规则推进流程。"""

    return handle_task_action(task_id, RECORD_ACTION_APPROVE, request, db)


@router.post(
    "/approval-tasks/{task_id}/reject",
    response_model=Result[ApprovalActionResponse],
    summary="拒绝审批任务",
)
def reject_approval_task(
    task_id: UUID,
    request: ApprovalTaskActionRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[ApprovalActionResponse]:
    """拒绝分配给当前人员的待办任务，实例立即结束为已拒绝。"""

    return handle_task_action(task_id, RECORD_ACTION_REJECT, request, db)


def handle_task_action(
    task_id: UUID,
    action: str,
    request: ApprovalTaskActionRequest,
    db: Session,
) -> Result[ApprovalActionResponse]:
    """把同意和拒绝两个入口收敛到同一套领域异常处理。"""

    try:
        view = approval_task_service.handle_task(task_id, action, request, db)
        return Result.success(build_action_response(view))
    except (
        ApprovalNotFoundError,
        ApprovalPermissionError,
        ApprovalStateError,
        ProcessStateError,
    ) as exc:
        raise_process_http_error(exc)
