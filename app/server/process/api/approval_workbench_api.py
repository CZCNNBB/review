"""审批与抄送统一工作台列表接口。"""

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.common.schemas.result import Result
from app.common.security import verify_admin_key
from app.server.process.src.schemas.approval_schema import ApprovalWorkItemResponse
from app.server.process.src.service.approval_workbench_service import (
    ApprovalWorkbenchService,
)


router = APIRouter()
workbench_service = ApprovalWorkbenchService()


@router.get(
    "/work-items",
    response_model=Result[list[ApprovalWorkItemResponse]],
    dependencies=[Depends(verify_admin_key)],
    summary="查询审批与抄送统一工作台",
)
def list_work_items(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=500),
    db: Session = Depends(get_postgres_engine),
) -> Result[list[ApprovalWorkItemResponse]]:
    """从统一任务表分页读取两类任务，并提供审批单与节点展示字段。"""

    items = workbench_service.list_items(db, offset, limit)
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
            )
            for item in items
        ]
    )
