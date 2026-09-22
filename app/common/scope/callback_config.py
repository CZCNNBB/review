"""审批中心回调业务系统时所需的租户配置端口。

业务执行子模块位于 process 模块，但回调基础地址和 Service Token 属于 tenant 模块。
process 只依赖这里定义的 CallbackTargetResolver 端口，具体实现由 tenant 模块在
``tenant/src/scope/`` 中提供，装配方式与 ResourceScope 保持一致：process 不查询任何
tenant 表，也不导入 tenant 的 Repository 或 Service。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from uuid import UUID

from sqlmodel import Session


class CallbackTargetUnavailableError(Exception):
    """当前审批实例没有可用的回调配置，不能发起业务执行请求。

    异常信息会作为执行记录的失败摘要保存，因此实现方需要给出可以直接展示给后台
    人员的中文原因，并且不能包含 Token 明文。
    """


@dataclass(frozen=True)
class CallbackTarget:
    """一次业务执行请求所需的租户回调目标。

    token 只在构造请求头时短暂存在于内存中，不写入执行记录、不写入日志，也不返回给
    任何查询接口。__repr__ 被重写以避免调试输出意外带出凭据明文。
    """

    tenant_id: UUID
    base_url: str
    header_name: str
    token_prefix: str
    token: str = field(repr=False)

    def build_url(self, relative_path: str) -> str:
        """把租户回调基础地址和业务动作相对路径拼成最终请求地址。

        基础地址在租户模块保存时已经去掉末尾斜杠，相对路径在业务动作保存时已经确认
        以单个斜杠开头，这里仍然做一次容错处理，避免手工改库后拼出双斜杠。
        """

        return f"{self.base_url.rstrip('/')}/{relative_path.lstrip('/')}"

    def build_headers(self) -> dict[str, str]:
        """在内存中构造认证请求头，复用业务系统现有的认证方式。

        token_prefix 允许为空，此时只发送 Token 明文，适配不使用 Bearer 前缀的
        业务系统认证头。
        """

        if not self.token_prefix:
            return {self.header_name: self.token}
        return {self.header_name: f"{self.token_prefix} {self.token}".strip()}


# 全局模式下没有租户归属，业务执行无法解析回调目标。发起审批接口已经在全局模式下
# 拒绝 action_code，这里保留提示用于兜住运行中切换租户开关的场景。
GLOBAL_CALLBACK_TARGET_MESSAGE = "当前运行在全局模式，没有可用的租户回调配置"


class CallbackTargetResolver(ABC):
    """按审批实例解析租户回调地址和 Service Token。"""

    @abstractmethod
    def resolve(self, approval_instance_id: UUID, db: Session) -> CallbackTarget:
        """返回回调目标，配置缺失、停用或过期时抛出 CallbackTargetUnavailableError。"""


class GlobalCallbackTargetResolver(CallbackTargetResolver):
    """未启用租户能力时使用的空操作实现。"""

    def resolve(self, approval_instance_id: UUID, db: Session) -> CallbackTarget:
        """全局模式没有租户配置，直接说明当前部署不支持业务执行。"""

        raise CallbackTargetUnavailableError(GLOBAL_CALLBACK_TARGET_MESSAGE)
