"""租户业务接入授权与审批使用记录的请求响应模型。"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# 授权记录只有启用和停用两种状态，停用后不影响已经运行的审批实例。
BINDING_STATUS_PATTERN = r"^(ENABLED|DISABLED)$"


class ProcessBindingCreateRequest(BaseModel):
    """创建租户流程授权请求。"""

    process_id: UUID


class BusinessActionBindingCreateRequest(BaseModel):
    """创建租户业务动作授权请求。"""

    business_action_id: UUID


class BindingStatusUpdateRequest(BaseModel):
    """启停租户资源授权请求。

    第一版只允许切换 ENABLED、DISABLED，不提供物理删除，保证历史授权关系可追溯。
    """

    status: str = Field(pattern=BINDING_STATUS_PATTERN)


class ProcessBindingResponse(BaseModel):
    """租户流程授权响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    process_id: UUID
    status: str
    created_at: datetime
    updated_at: datetime


class BusinessActionBindingResponse(BaseModel):
    """租户业务动作授权响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    business_action_id: UUID
    status: str
    created_at: datetime
    updated_at: datetime


class ProcessUsageRecordResponse(BaseModel):
    """租户审批使用记录响应。

    使用记录本身只保存归属和关联信息，审批状态、当前节点和耗时在查询时从 process
    运行表读取后组装，不写回使用记录表。
    """

    id: UUID
    tenant_id: UUID
    process_id: UUID
    process_version_id: UUID
    approval_instance_id: UUID
    business_key: str
    action_code: Optional[str]
    created_at: datetime
    approval_status: Optional[str]
    approval_title: Optional[str]
    current_node_name: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    duration_ms: Optional[int]
