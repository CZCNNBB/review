"""审批与抄送统一工作台列表接口。"""

from enum import Enum
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.common.schemas.result import Result
from app.common.security import verify_admin_key
from app.server.process.api.approval_instance_api import build_detail_response
from app.server.process.api.process_api import raise_process_http_error
from app.server.process.src.constants import (
    TASK_STATUS_APPROVED,
    TASK_STATUS_CANCELLED,
    TASK_STATUS_PENDING,
    TASK_STATUS_RECEIVED,
    TASK_STATUS_REJECTED,
    TASK_TYPE_APPROVAL,
    TASK_TYPE_COPY,
)
from app.server.process.src.schemas.approval_schema import (
    ApprovalInstanceDetailResponse,
    ApprovalWorkItemResponse,
)
from app.server.process.src.service.approval_workbench_service import (
    ApprovalWorkbenchService,
)
from app.server.process.src.utils.duration import elapsed_ms
from app.server.process.src.service.exceptions import (
    ApprovalNotFoundError,
    ApprovalPermissionError,
)


router = APIRouter()
workbench_service = ApprovalWorkbenchService()


class WorkItemTypeFilter(str, Enum):
    """工作台可查询的任务类型。"""

    APPROVAL = TASK_TYPE_APPROVAL
    COPY = TASK_TYPE_COPY


class WorkItemStatusFilter(str, Enum):
    """任务状态筛选；COMPLETED 表示所有无需再处理的终态。"""

    PENDING = TASK_STATUS_PENDING
    COMPLETED = "COMPLETED"
    APPROVED = TASK_STATUS_APPROVED
    REJECTED = TASK_STATUS_REJECTED
    CANCELLED = TASK_STATUS_CANCELLED
    RECEIVED = TASK_STATUS_RECEIVED


def statuses_for_filter(status: WorkItemStatusFilter | None) -> list[str]:
    """把已完成这一跨类型筛选值展开为数据库中的实际任务状态。"""

    if status is None:
        return []
    if status == WorkItemStatusFilter.COMPLETED:
        return [
            TASK_STATUS_APPROVED,
            TASK_STATUS_REJECTED,
            TASK_STATUS_CANCELLED,
            TASK_STATUS_RECEIVED,
        ]
    return [status.value]


@router.get(
    "/work-items",
    response_model=Result[list[ApprovalWorkItemResponse]],
    dependencies=[Depends(verify_admin_key)],
    summary="查询审批与抄送统一工作台",
)
def list_work_items(
    person_id: UUID | None = Query(default=None, description="可选的任务接收人 ID"),
    task_type: WorkItemTypeFilter | None = Query(default=None, description="APPROVAL 或 COPY"),
    status: WorkItemStatusFilter | None = Query(default=None, description="任务状态或 COMPLETED"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=500),
    db: Session = Depends(get_postgres_engine),
) -> Result[list[ApprovalWorkItemResponse]]:
    """统一筛选和分页审批、抄送任务，并提供审批单与节点展示字段。"""

    items = workbench_service.list_items(
        db,
        person_id=person_id,
        task_type=task_type.value if task_type else None,
        statuses=statuses_for_filter(status),
        offset=offset,
        limit=limit,
    )
    return Result.success(
        [
            ApprovalWorkItemResponse(
                id=item.task.id,
                task_type=item.task.task_type,
                instance_id=item.task.instance_id,
                instance_title=item.instance.title,
                business_key=item.instance.business_key,
                node_name=item.execution.node_name,
                person_id=item.task.recipient_person_id,
                person_snapshot=dict(item.task.recipient_snapshot_json or {}),
                task_status=item.task.status,
                instance_status=item.instance.status,
                created_at=item.task.created_at,
                handled_at=item.task.handled_at,
                cancelled_at=item.task.cancelled_at,
                duration_ms=elapsed_ms(
                    item.task.created_at,
                    item.task.handled_at or item.task.cancelled_at,
                ),
            )
            for item in items
        ]
    )


@router.get(
    "/work-items/{task_id}/instance",
    response_model=Result[ApprovalInstanceDetailResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="查看任务关联的审批单",
)
def get_work_item_instance(
    task_id: UUID,
    person_id: UUID = Query(description="任务接收人 ID"),
    db: Session = Depends(get_postgres_engine),
) -> Result[ApprovalInstanceDetailResponse]:
    """验证审批或抄送任务归属后，返回关联审批单的只读详情。"""

    try:
        view = workbench_service.get_recipient_instance_view(task_id, person_id, db)
        return Result.success(build_detail_response(view))
    except (ApprovalNotFoundError, ApprovalPermissionError) as exc:
        raise_process_http_error(exc)
