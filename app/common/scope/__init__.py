"""业务资源作用域和回调配置抽象导出。"""

from app.common.scope.callback_config import (
    CallbackTargetUnavailableError,
    CallbackTarget,
    CallbackTargetResolver,
    GlobalCallbackTargetResolver,
)
from app.common.scope.resource_scope import GlobalResourceScope, ResourceScope

__all__ = [
    "CallbackTargetUnavailableError",
    "CallbackTarget",
    "CallbackTargetResolver",
    "GlobalCallbackTargetResolver",
    "GlobalResourceScope",
    "ResourceScope",
]
