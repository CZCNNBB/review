"""审批实例发起、详情和运行时间线接口。"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.common.schemas.result import Result
from app.server.process.api.approval_view_builder import (
    build_node_execution_response,
    build_node_name_index,
    build_record_response,
    build_task_response,
)
from app.server.process.api.process_api import raise_process_http_error
from app.server.process.src.constants import TASK_STATUS_PENDING
from app.server.process.src.schemas.approval_schema import (
    ApprovalInstanceDetailResponse,
    ApprovalInstanceStartedResponse,
    ApprovalNodeExecutionResponse,
    ApprovalRecordResponse,
    ApprovalStartRequest,
    ApprovalTaskResponse,
    ApprovalTimelineEntryResponse,
    ApprovalTimelineResponse,
)
from app.server.process.src.service.approval_instance_service import (
    ApprovalInstanceService,
    InstanceDetailView,
    StartedInstance,
)
from app.server.process.src.service.exceptions import (
    ApprovalNotFoundError,
    ProcessConflictError,
    ProcessNotFoundError,
    ProcessStateError,
    ProcessValidationError,
)
from app.server.process.src.utils.duration import elapsed_ms


router = APIRouter()
approval_instance_service = ApprovalInstanceService()


def build_started_response(started: StartedInstance) -> ApprovalInstanceStartedResponse:
    """把发起审批的结果转换成响应。"""

    current_node_execution = started.current_node_execution
    return ApprovalInstanceStartedResponse(
        instance_id=started.instance.id,
        status=started.instance.status,
        process_id=started.instance.process_id,
        process_version_id=started.version.id,
        process_version_no=started.version.version_no,
        current_node_name=(
            current_node_execution.node_name if current_node_execution else None
        ),
        pending_approver_person_ids=list(started.pending_approver_person_ids),
        started_at=started.instance.started_at,
        idempotent_replay=started.idempotent_replay,
    )


def build_instance_responses(
    view: InstanceDetailView,
) -> tuple[
    list[ApprovalNodeExecutionResponse],
    list[ApprovalTaskResponse],
    list[ApprovalRecordResponse],
]:
    """把实例、节点、任务和审批记录批量转换成响应，供详情和时间线复用。"""

    node_name_by_node_id = build_node_name_index(view.node_executions)
    node_name_by_execution_id = {
        execution.id: execution.node_name for execution in view.node_executions
    }

    node_execution_responses = [
        build_node_execution_response(execution, node_name_by_node_id)
        for execution in view.node_executions
    ]
    task_responses = [
        build_task_response(
            task,
            instance_title=view.instance.title,
            business_key=view.instance.business_key,
            node_name=node_name_by_execution_id.get(task.node_execution_id),
        )
        for task in view.tasks
    ]
    task_created_at = {task.id: task.created_at for task in view.tasks}
    record_responses = [
        build_record_response(record, task_created_at) for record in view.records
    ]
    return node_execution_responses, task_responses, record_responses


def build_detail_response(view: InstanceDetailView) -> ApprovalInstanceDetailResponse:
    """组装审批详情响应。"""

    node_responses, task_responses, record_responses = build_instance_responses(view)

    current_node = None
    if view.instance.current_node_execution_id is not None:
        current_node = next(
            (
                response
                for response in node_responses
                if response.id == view.instance.current_node_execution_id
            ),
            None,
        )

    return ApprovalInstanceDetailResponse(
        id=view.instance.id,
        process_id=view.instance.process_id,
        # 流程名称取实例绑定版本的名称，后续发布新版本不会改变历史实例的展示。
        process_name=view.version.name,
        process_version_id=view.version.id,
        process_version_no=view.version.version_no,
        business_key=view.instance.business_key,
        title=view.instance.title,
        applicant_person_id=view.instance.applicant_person_id,
        applicant_snapshot=dict(view.instance.applicant_snapshot_json or {}),
        action_code=view.instance.action_code,
        status=view.instance.status,
        approval_form=dict(view.instance.approval_form_json or {}),
        current_node=current_node,
        node_executions=node_responses,
        tasks=task_responses,
        records=record_responses,
        pending_tasks=[
            response
            for response, task in zip(task_responses, view.tasks)
            if task.status == TASK_STATUS_PENDING
        ],
        started_at=view.instance.started_at,
        finished_at=view.instance.finished_at,
        duration_ms=elapsed_ms(view.instance.started_at, view.instance.finished_at),
        created_at=view.instance.created_at,
        updated_at=view.instance.updated_at,
    )


def build_timeline_response(view: InstanceDetailView) -> ApprovalTimelineResponse:
    """按实际执行顺序组装运行时间线，每个节点带上自己的任务和审批记录。"""

    node_responses, task_responses, record_responses = build_instance_responses(view)
    task_responses_by_execution: dict[UUID, list[ApprovalTaskResponse]] = {}
    for task, response in zip(view.tasks, task_responses):
        task_responses_by_execution.setdefault(task.node_execution_id, []).append(
            response
        )
    record_responses_by_execution: dict[UUID, list[ApprovalRecordResponse]] = {}
    for record, response in zip(view.records, record_responses):
        record_responses_by_execution.setdefault(record.node_execution_id, []).append(
            response
        )

    entries = [
        ApprovalTimelineEntryResponse(
            node_execution=response,
            tasks=task_responses_by_execution.get(execution.id, []),
            records=record_responses_by_execution.get(execution.id, []),
        )
        for execution, response in zip(view.node_executions, node_responses)
    ]

    return ApprovalTimelineResponse(
        instance_id=view.instance.id,
        title=view.instance.title,
        status=view.instance.status,
        started_at=view.instance.started_at,
        finished_at=view.instance.finished_at,
        duration_ms=elapsed_ms(view.instance.started_at, view.instance.finished_at),
        entries=entries,
    )


@router.post(
    "/processes/{process_id}/instances",
    response_model=Result[ApprovalInstanceStartedResponse],
    status_code=status.HTTP_201_CREATED,
    summary="发起审批",
)
def start_approval_instance(
    process_id: UUID,
    request: ApprovalStartRequest,
    db: Session = Depends(get_postgres_engine),
) -> Result[ApprovalInstanceStartedResponse]:
    """按流程当前已发布版本创建审批实例。

    业务系统只传 process_id 和业务数据，版本由审批中心自动确定。相同幂等键重复
    发起时返回原审批实例。
    """

    try:
        started = approval_instance_service.start_instance(process_id, request, db)
        return Result.success(build_started_response(started))
    except (
        ProcessNotFoundError,
        ProcessStateError,
        ProcessConflictError,
        ProcessValidationError,
    ) as exc:
        raise_process_http_error(exc)


@router.get(
    "/approval-instances/{instance_id}",
    response_model=Result[ApprovalInstanceDetailResponse],
    summary="查询审批详情",
)
def get_approval_instance(
    instance_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[ApprovalInstanceDetailResponse]:
    """查询审批实例的当前状态、节点耗时和处理过程。"""

    try:
        view = approval_instance_service.get_instance_view(instance_id, db)
        return Result.success(build_detail_response(view))
    except ApprovalNotFoundError as exc:
        raise_process_http_error(exc)


@router.get(
    "/approval-instances/{instance_id}/timeline",
    response_model=Result[ApprovalTimelineResponse],
    summary="查询审批运行时间线",
)
def get_approval_instance_timeline(
    instance_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> Result[ApprovalTimelineResponse]:
    """按实际执行顺序返回经过的节点、任务和审批记录。"""

    try:
        view = approval_instance_service.get_instance_view(instance_id, db)
        return Result.success(build_timeline_response(view))
    except ApprovalNotFoundError as exc:
        raise_process_http_error(exc)
