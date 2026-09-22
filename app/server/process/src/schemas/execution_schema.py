"""业务执行记录的响应模型。

响应里只出现动作配置快照和本次调用结果，不包含 Service Token、加密密文和完整认证
请求头。认证信息只存在于执行器发送请求前的内存中。
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


class ExecutionRecordResponse(BaseModel):
    """执行记录列表项。

    列表用于后台筛选核对，因此只返回定位和结果字段。响应正文、请求参数这类体积较大
    的内容放在详情响应里，避免列表页一次加载过多数据。
    """

    id: UUID
    approval_instance_id: UUID
    action_code: str
    http_method: Optional[str]
    relative_path: Optional[str]
    status: str
    http_status_code: Optional[int]
    error_message: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    duration_ms: Optional[int]
    created_at: datetime


class ExecutionRecordDetailResponse(ExecutionRecordResponse):
    """执行记录详情，供后台核对本次调用的完整配置和响应内容。"""

    business_action_id: Optional[UUID]
    request_url: Optional[str]
    timeout_ms: Optional[int]
    success_status_codes: list[int]
    request_payload: dict[str, Any]
    # 响应正文在保存时已经按固定上限截断，明细页直接展示保存的内容。
    response_body: Optional[str]
    updated_at: datetime
