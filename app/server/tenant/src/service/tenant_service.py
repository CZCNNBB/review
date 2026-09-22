"""租户注册、凭据管理和 API Key 认证业务逻辑。"""

from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.server.tenant.src.models.tenant_model import (
    Tenant,
    TenantApiKey,
    TenantCallbackCredential,
)
from app.server.tenant.src.repository.tenant_repository import TenantRepository
from app.server.tenant.src.schemas.tenant_schema import TenantCreateRequest, TenantUpdateRequest
from app.server.tenant.src.service.exceptions import (
    CredentialConfigurationError,
    CredentialNotFoundError,
    InvalidApiKeyError,
    TenantConflictError,
    TenantNotFoundError,
)
from app.server.tenant.src.utils.credential import (
    CredentialCipher,
    generate_api_key,
    is_expired,
    utc_now,
)


class TenantService:
    """提供租户、API Key 和回调 Service Token 凭据的业务能力。"""

    def __init__(self, repository: TenantRepository | None = None):
        """初始化租户服务并允许测试注入 Repository。"""

        self.repository = repository or TenantRepository()

    def create_tenant(self, request: TenantCreateRequest, db: Session) -> Tenant:
        """创建新的业务系统租户。"""

        existing_tenant = self.repository.get_tenant_by_code(request.code, db)
        if existing_tenant:
            raise TenantConflictError(f"租户编码 {request.code} 已存在")

        tenant = Tenant(
            code=request.code,
            name=request.name.strip(),
            description=request.description.strip() if request.description else None,
            callback_base_url=str(request.callback_base_url).rstrip("/"),
        )
        self.repository.add_tenant(tenant, db)
        self._commit_or_conflict(db, "租户编码已存在")
        db.refresh(tenant)
        return tenant

    def list_tenants(self, db: Session, offset: int = 0, limit: int = 100) -> list[Tenant]:
        """分页查询租户列表。"""

        return self.repository.list_tenants(db, offset=offset, limit=limit)

    def get_tenant(self, tenant_id: UUID, db: Session) -> Tenant:
        """查询租户，不存在时抛出领域异常。"""

        tenant = self.repository.get_tenant_by_id(tenant_id, db)
        if not tenant:
            raise TenantNotFoundError("租户不存在")
        return tenant

    def update_tenant(self, tenant_id: UUID, request: TenantUpdateRequest, db: Session) -> Tenant:
        """更新租户基本信息、回调基础地址或状态。"""

        tenant = self.get_tenant(tenant_id, db)
        update_data = request.model_dump(exclude_unset=True)

        # URL 对象不可直接写入数据库，统一转换并清理末尾斜杠，便于后续拼接动作路径。
        if "callback_base_url" in update_data:
            update_data["callback_base_url"] = str(update_data["callback_base_url"]).rstrip("/")
        if "name" in update_data:
            update_data["name"] = update_data["name"].strip()
        if update_data.get("description"):
            update_data["description"] = update_data["description"].strip()

        for field_name, field_value in update_data.items():
            setattr(tenant, field_name, field_value)
        tenant.updated_at = utc_now()
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        return tenant

    def create_api_key(
        self,
        tenant_id: UUID,
        name: str,
        expires_at: datetime | None,
        db: Session,
    ) -> TenantApiKey:
        """为租户生成新的 API Key，并以明文保存。"""

        self.get_tenant(tenant_id, db)
        generated_key = generate_api_key()
        api_key = TenantApiKey(
            tenant_id=tenant_id,
            name=name.strip(),
            api_key=generated_key,
            expires_at=expires_at,
        )
        self.repository.add_api_key(api_key, db)
        self._commit_or_conflict(db, "API Key 冲突，请重试")
        db.refresh(api_key)
        return api_key

    def list_api_keys(self, tenant_id: UUID, db: Session) -> list[TenantApiKey]:
        """查询租户 API Key，包含管理页面所需的明文。"""

        self.get_tenant(tenant_id, db)
        return self.repository.list_api_keys(tenant_id, db)

    def revoke_api_key(self, tenant_id: UUID, api_key_id: UUID, db: Session) -> TenantApiKey:
        """撤销租户 API Key，撤销操作不可恢复。"""

        api_key = self.repository.get_api_key_by_id(api_key_id, db)
        if not api_key or api_key.tenant_id != tenant_id:
            raise CredentialNotFoundError("API Key 不存在")
        if api_key.status != "REVOKED":
            api_key.status = "REVOKED"
            api_key.revoked_at = utc_now()
            db.add(api_key)
            db.commit()
            db.refresh(api_key)
        return api_key

    def authenticate_api_key(self, plaintext_api_key: str, db: Session) -> tuple[Tenant, TenantApiKey]:
        """验证 API Key 并返回可信租户上下文。"""

        if not plaintext_api_key:
            raise InvalidApiKeyError("API Key 格式错误")

        api_key = self.repository.get_api_key_by_value(plaintext_api_key, db)
        if not api_key:
            raise InvalidApiKeyError("API Key 无效")
        if api_key.status != "ACTIVE":
            raise InvalidApiKeyError("API Key 已停用或撤销")
        if is_expired(api_key.expires_at):
            raise InvalidApiKeyError("API Key 已过期")

        tenant = self.get_tenant(api_key.tenant_id, db)
        if tenant.status != "ENABLED":
            raise InvalidApiKeyError("租户已停用")

        # 第一版直接记录最近使用时间；调用量增大后可改为异步或限频更新。
        api_key.last_used_at = utc_now()
        db.add(api_key)
        db.commit()
        db.refresh(api_key)
        return tenant, api_key

    def create_callback_credential(
        self,
        tenant_id: UUID,
        name: str,
        token: str,
        header_name: str,
        token_prefix: str,
        expires_at: datetime | None,
        db: Session,
    ) -> TenantCallbackCredential:
        """保存业务系统签发的 Service Token，并替换租户原有的有效凭据。

        一个租户同一时间只允许存在一个 ACTIVE 凭据，因此撤销旧凭据和写入新凭据必须在
        同一个事务中完成，避免出现两个有效凭据或没有可用凭据的中间状态。Token 只以
        密文落库，返回值里不含明文。
        """

        self.get_tenant(tenant_id, db)
        try:
            cipher = CredentialCipher.from_environment()
            token_ciphertext = cipher.encrypt(token)
        except ValueError as exc:
            raise CredentialConfigurationError(str(exc)) from exc

        now = utc_now()
        existing_credential = self.repository.get_active_callback_credential(
            tenant_id,
            db,
        )
        if existing_credential is not None:
            existing_credential.status = "REVOKED"
            existing_credential.revoked_at = now
            db.add(existing_credential)

        credential = TenantCallbackCredential(
            tenant_id=tenant_id,
            name=name.strip(),
            header_name=header_name,
            token_prefix=token_prefix,
            token_ciphertext=token_ciphertext,
            expires_at=expires_at,
        )
        self.repository.add_callback_credential(credential, db)
        self._commit_or_conflict(db, "回调凭据写入冲突，请重试")
        db.refresh(credential)
        return credential

    def list_callback_credentials(
        self,
        tenant_id: UUID,
        db: Session,
    ) -> list[TenantCallbackCredential]:
        """查询租户回调 Service Token 凭据元数据。"""

        self.get_tenant(tenant_id, db)
        return self.repository.list_callback_credentials(tenant_id, db)

    def revoke_callback_credential(
        self,
        tenant_id: UUID,
        credential_id: UUID,
        db: Session,
    ) -> TenantCallbackCredential:
        """撤销回调 Service Token 凭据，撤销后不能恢复。"""

        credential = self.repository.get_callback_credential_by_id(credential_id, db)
        if not credential or credential.tenant_id != tenant_id:
            raise CredentialNotFoundError("回调凭据不存在")
        if credential.status != "REVOKED":
            credential.status = "REVOKED"
            credential.revoked_at = utc_now()
            db.add(credential)
            db.commit()
            db.refresh(credential)
        return credential

    @staticmethod
    def _commit_or_conflict(db: Session, message: str) -> None:
        """提交事务，并将数据库唯一约束错误转换为领域冲突。"""

        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise TenantConflictError(message) from exc
