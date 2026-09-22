"""业务接入接口使用的租户身份和资源作用域组合。"""

from dataclasses import dataclass
from uuid import UUID

from app.common.scope import ResourceScope
from app.server.tenant.src.scope.tenant_scope import (
    RESOURCE_APPROVAL_INSTANCE,
    RESOURCE_BUSINESS_ACTION,
    RESOURCE_PROCESS,
    create_resource_scope,
)


@dataclass(frozen=True)
class BusinessAccessContext:
    """一次业务接入请求的可信租户身份和三类资源作用域。

    tenant_id 为空表示当前运行在全局模式，三类作用域都是空操作实现，接口既不要求
    API Key，也不会读写任何 tenant 表。
    """

    tenant_id: UUID | None
    process_scope: ResourceScope
    action_scope: ResourceScope
    instance_scope: ResourceScope


def create_business_access_context(tenant_id: UUID | None) -> BusinessAccessContext:
    """按当前租户开关构造业务接入上下文。

    三类作用域在一次请求中同时创建，保证业务服务不需要自己判断租户模式，也不需要
    重复解析 API Key。
    """

    return BusinessAccessContext(
        tenant_id=tenant_id,
        process_scope=create_resource_scope(RESOURCE_PROCESS, tenant_id),
        action_scope=create_resource_scope(RESOURCE_BUSINESS_ACTION, tenant_id),
        instance_scope=create_resource_scope(RESOURCE_APPROVAL_INSTANCE, tenant_id),
    )
