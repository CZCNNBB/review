"""审批单抄送收件箱和收件人只读详情接口。"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.common.schemas.result import Result
from app.common.security import verify_admin_key
from app.server.process.api.approval_instance_api import build_detail_response
from app.server.process.api.process_api import raise_process_http_error
from app.server.process.src.schemas.approval_schema import (
    ApprovalCopyResponse,
    ApprovalInstanceDetailResponse,
)
from app.server.process.src.service.approval_copy_service import ApprovalCopyService
from app.server.process.src.service.exceptions import (
    ApprovalNotFoundError,
    ApprovalPermissionError,
)


router = APIRouter()
approval_copy_service = ApprovalCopyService()


@router.get(
    "/approval-copies",
    response_model=Result[list[ApprovalCopyResponse]],
    dependencies=[Depends(verify_admin_key)],
    summary="查询收到的审批单抄送",
)
def list_approval_copies(
    person_id: UUID | None = Query(default=None, description="可选的抄送收件人 ID"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_postgres_engine),
) -> Result[list[ApprovalCopyResponse]]:
    """默认查询全部抄送记录，也可按收件人筛选。"""

    items = approval_copy_service.list_person_copies(person_id, db, offset, limit)
    return Result.success(
        [
            ApprovalCopyResponse(
                id=item.copy.id,
                instance_id=item.copy.instance_id,
                instance_title=item.instance.title,
                business_key=item.instance.business_key,
                instance_status=item.instance.status,
                node_name=item.execution.node_name,
                recipient_person_id=item.copy.recipient_person_id,
                recipient_snapshot=dict(item.copy.recipient_snapshot_json or {}),
                created_at=item.copy.created_at,
            )
            for item in items
        ]
    )


@router.get(
    "/approval-copies/{copy_id}/instance",
    response_model=Result[ApprovalInstanceDetailResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="查看抄送给我的审批单",
)
def get_copied_instance(
    copy_id: UUID,
    person_id: UUID = Query(description="抄送收件人 ID"),
    db: Session = Depends(get_postgres_engine),
) -> Result[ApprovalInstanceDetailResponse]:
    """校验收件人身份后返回审批单只读详情，不提供审批操作。"""

    try:
        view = approval_copy_service.get_recipient_instance_view(copy_id, person_id, db)
        return Result.success(build_detail_response(view))
    except (ApprovalNotFoundError, ApprovalPermissionError) as exc:
        raise_process_http_error(exc)
