"""基于审批使用记录和回调凭据实现业务执行回调目标解析。

业务执行子模块位于 process 模块，但它需要租户的回调地址和 Service Token。这里把
tenant 模块的实现注册到 ``app.common.scope`` 定义的 CallbackTargetResolver 端口上，
process 只依赖端口，既不查询任何 tenant 表，也不导入 tenant 的 Repository。
"""

from uuid import UUID

from sqlmodel import Session

from app.common.scope import (
    CallbackTargetUnavailableError,
    CallbackTarget,
    CallbackTargetResolver,
    GlobalCallbackTargetResolver,
)
from app.server.tenant.src.repository.tenant_binding_repository import (
    TenantBindingRepository,
)
from app.server.tenant.src.repository.tenant_repository import TenantRepository
from app.server.tenant.src.scope.tenant_scope import is_tenancy_enabled
from app.server.tenant.src.utils.credential import CredentialCipher, is_expired


class TenantCallbackTargetResolver(CallbackTargetResolver):
    """通过审批使用记录确定租户，再读取回调地址和唯一有效的 Service Token。"""

    def __init__(
        self,
        binding_repository: TenantBindingRepository | None = None,
        tenant_repository: TenantRepository | None = None,
        cipher: CredentialCipher | None = None,
    ):
        """初始化回调配置实现并允许测试注入依赖。"""

        self.binding_repository = binding_repository or TenantBindingRepository()
        self.tenant_repository = tenant_repository or TenantRepository()
        # 主密钥缺失时不在构造阶段抛错，避免 Worker 未启用时应用无法启动。
        self._cipher = cipher

    def resolve(self, approval_instance_id: UUID, db: Session) -> CallbackTarget:
        """解析审批实例的租户回调目标。

        解析顺序固定为：使用记录、租户状态、唯一有效的 Service Token。任何一步失败都
        转换成可以直接写进执行记录的失败摘要，不把 Token 相关内容带进异常信息。
        """

        usage_record = self.binding_repository.get_usage_record_by_instance_id(
            approval_instance_id,
            db,
        )
        if usage_record is None:
            raise CallbackTargetUnavailableError(
                "找不到该审批实例的租户使用记录，无法确定回调地址"
            )

        tenant = self.tenant_repository.get_tenant_by_id(usage_record.tenant_id, db)
        if tenant is None:
            raise CallbackTargetUnavailableError("审批实例所属租户不存在")
        if tenant.status != "ENABLED":
            raise CallbackTargetUnavailableError("租户已停用，不再发出业务执行请求")

        credential = self.tenant_repository.get_active_callback_credential(tenant.id, db)
        if credential is None:
            raise CallbackTargetUnavailableError(
                "租户没有可用的 Service Token 凭据，无法回调业务系统"
            )
        if is_expired(credential.expires_at):
            raise CallbackTargetUnavailableError(
                "租户 Service Token 凭据已过期，请重新配置"
            )

        return CallbackTarget(
            tenant_id=tenant.id,
            base_url=tenant.callback_base_url,
            header_name=credential.header_name,
            token_prefix=credential.token_prefix,
            token=self._decrypt(credential.token_ciphertext),
        )

    def _decrypt(self, token_ciphertext: str) -> str:
        """只在发送请求前解密 Service Token，解密失败时给出明确失败原因。"""

        cipher = self._cipher
        if cipher is None:
            try:
                cipher = CredentialCipher.from_environment()
            except ValueError as exc:
                raise CallbackTargetUnavailableError(str(exc)) from exc

        try:
            return cipher.decrypt(token_ciphertext)
        except ValueError as exc:
            raise CallbackTargetUnavailableError(str(exc)) from exc


def create_callback_target_resolver() -> CallbackTargetResolver:
    """根据租户开关创建回调目标解析实现，全局模式返回空操作实现。"""

    if not is_tenancy_enabled():
        return GlobalCallbackTargetResolver()
    return TenantCallbackTargetResolver()
