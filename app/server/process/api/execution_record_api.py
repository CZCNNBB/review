"""业务执行记录管理接口。

后台人员通过这些接口核对审批通过后业务系统是否真的被调用，以及调用的实际结果。查询
响应不返回 Service Token、密文和完整认证请求头，响应正文在保存时已经按上限截断。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.common.schemas.result import Result
from app.common.security import verify_admin_key
from app.server.process.api.execution_view_builder import (
    build_execution_record_detail_response,
    build_execution_record_response,
)
from app.server.process.api.process_api import raise_process_http_error
from app.server.process.src.constants import EXECUTION_STATUS_PATTERN
from app.server.process.src.schemas.execution_schema import (
    ExecutionRecordDetailResponse,
    ExecutionRecordResponse,
)
from app.server.process.src.service.business_execution_service import (
    BusinessExecutionService,
)
from app.server.process.src.service.exceptions import ExecutionRecordNotFoundError


router = APIRouter()
business_execution_service = BusinessExecutionService()


@router.get(
    "/admin/execution-records",
    response_model=Result[list[ExecutionRecordResponse]],
    dependencies=[Depends(verify_admin_key)],
    summary="查询业务执行记录列表",
)
def list_execution_records(
    approval_instance_id: UUID | None = Query(default=None),
    action_code: str | None = Query(default=None, max_length=100),
    record_status: str | None = Query(
        default=None,
        alias="status",
        pattern=EXECUTION_STATUS_PATTERN,
    ),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_postgres_engine),
) -> Result[list[ExecutionRecordResponse]]:
    """分页查询执行记录，可按审批实例、业务动作和执行状态筛选。"""

    records = business_execution_service.list_records(
        db,
        approval_instance_id=approval_instance_id,
        action_code=action_code,
        status=record_status,
        offset=offset,
        limit=limit,
    )
    return Result.success(
        [build_execution_record_response(record) for record in records]
    )


@router.get(
    "/admin/execution-records/{record_id}",
    response_model=Result[ExecutionRecordDetailResponse],
    dependencies=[Depends(verify_admin_key)],
    summary="查询业务执行记录详情",
)
def get_execution_record(
    record_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[ExecutionRecordDetailResponse]:
    """按主键查询执行记录详情，包含请求参数和响应正文。"""

    try:
        record = business_execution_service.get_record(record_id, db)
        return Result.success(build_execution_record_detail_response(record))
    except ExecutionRecordNotFoundError as exc:
        raise_process_http_error(exc)
