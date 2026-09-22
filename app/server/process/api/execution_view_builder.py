"""业务执行记录响应组装。

审批详情页和执行记录查询接口共用这里的转换函数，保证同一份数据在两条链路上字段
完全一致。响应只包含动作配置快照和本次调用结果，不含 Service Token、密文和认证请求头。
"""

from app.server.process.src.models.execution_model import BusinessExecutionRecord
from app.server.process.src.schemas.execution_schema import (
    ExecutionRecordDetailResponse,
    ExecutionRecordResponse,
)
from app.server.process.src.utils.duration import elapsed_ms


def _base_fields(record: BusinessExecutionRecord) -> dict:
    """提取列表项和详情共用的字段。"""

    return {
        "id": record.id,
        "approval_instance_id": record.approval_instance_id,
        "action_code": record.action_code,
        "http_method": record.http_method,
        "relative_path": record.relative_path,
        "status": record.status,
        "http_status_code": record.http_status_code,
        "error_message": record.error_message,
        "started_at": record.started_at,
        "finished_at": record.finished_at,
        # 耗时不落库，统一由时间字段相减得到，避免两份数据不一致。
        "duration_ms": elapsed_ms(record.started_at, record.finished_at),
        "created_at": record.created_at,
    }


def build_execution_record_response(
    record: BusinessExecutionRecord,
) -> ExecutionRecordResponse:
    """组装执行记录列表项。"""

    return ExecutionRecordResponse(**_base_fields(record))


def build_execution_record_detail_response(
    record: BusinessExecutionRecord,
) -> ExecutionRecordDetailResponse:
    """组装执行记录详情，附带请求参数和截断后的响应正文。"""

    return ExecutionRecordDetailResponse(
        **_base_fields(record),
        business_action_id=record.business_action_id,
        request_url=record.request_url,
        timeout_ms=record.timeout_ms,
        success_status_codes=list(record.success_status_codes_json or []),
        request_payload=dict(record.request_payload_json or {}),
        response_body=record.response_body,
        updated_at=record.updated_at,
    )
