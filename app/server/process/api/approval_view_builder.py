"""审批运行接口的响应组装。

耗时统一在这里按时间字段计算：节点耗时取进入和离开时间之差，任务耗时取任务产生
到处理完成的时间之差。运行中的节点和待办任务按当前时间计算已耗时。
"""

from datetime import datetime
from typing import Mapping, Sequence
from uuid import UUID

from app.server.process.src.models.approval_model import (
    ApprovalNodeExecution,
    ApprovalRecord,
    ApprovalTask,
)
from app.server.process.src.schemas.approval_schema import (
    ApprovalNodeExecutionResponse,
    ApprovalRecordResponse,
    ApprovalTaskResponse,
)
from app.server.process.src.utils.duration import elapsed_ms


def build_node_name_index(
    executions: Sequence[ApprovalNodeExecution],
) -> dict[UUID, str]:
    """按版本节点 ID 建立节点名称索引，用于展示实际选择的后续节点。"""

    return {execution.node_id: execution.node_name for execution in executions}


def build_node_execution_response(
    execution: ApprovalNodeExecution,
    node_name_by_node_id: Mapping[UUID, str],
) -> ApprovalNodeExecutionResponse:
    """把节点执行记录转换为响应。"""

    result = dict(execution.result_json or {})
    raw_condition_hit = result.get("condition_hit")

    next_node_name = None
    if execution.next_node_id is not None:
        next_node_name = node_name_by_node_id.get(execution.next_node_id)

    return ApprovalNodeExecutionResponse(
        id=execution.id,
        node_id=execution.node_id,
        node_type=execution.node_type,
        node_name=execution.node_name,
        sequence_no=execution.sequence_no,
        status=execution.status,
        entered_at=execution.entered_at,
        completed_at=execution.completed_at,
        duration_ms=elapsed_ms(execution.entered_at, execution.completed_at),
        next_node_id=execution.next_node_id,
        next_node_name=next_node_name,
        condition_hit=raw_condition_hit if isinstance(raw_condition_hit, bool) else None,
        result=result,
    )


def build_task_response(
    task: ApprovalTask,
    *,
    instance_title: str | None = None,
    business_key: str | None = None,
    node_name: str | None = None,
) -> ApprovalTaskResponse:
    """把审批任务转换为响应。

    duration_ms 表示任务的停留时长：已经处理的任务是处理耗时，被系统取消的任务
    是等待到取消为止的时长，待办任务则是已经等待的时长。
    """

    # 取消的任务只有 cancelled_at，没有 handled_at，否则耗时会一直按当前时间增长。
    finished_at = task.handled_at or task.cancelled_at

    return ApprovalTaskResponse(
        id=task.id,
        instance_id=task.instance_id,
        node_execution_id=task.node_execution_id,
        instance_title=instance_title,
        business_key=business_key,
        node_name=node_name,
        approver_person_id=task.approver_person_id,
        approver_snapshot=dict(task.approver_snapshot_json or {}),
        status=task.status,
        created_at=task.created_at,
        handled_at=task.handled_at,
        cancelled_at=task.cancelled_at,
        duration_ms=elapsed_ms(task.created_at, finished_at),
    )


def build_record_response(
    record: ApprovalRecord,
    task_created_at: Mapping[UUID, datetime] | None = None,
) -> ApprovalRecordResponse:
    """把审批记录转换为响应，并补充审批人从收到待办到处理的耗时。"""

    created_at = None if task_created_at is None else task_created_at.get(record.task_id)

    return ApprovalRecordResponse(
        id=record.id,
        instance_id=record.instance_id,
        node_execution_id=record.node_execution_id,
        task_id=record.task_id,
        operator_person_id=record.operator_person_id,
        operator_snapshot=dict(record.operator_snapshot_json or {}),
        action=record.action,
        comment=record.comment,
        created_at=record.created_at,
        duration_ms=elapsed_ms(created_at, record.created_at),
    )
