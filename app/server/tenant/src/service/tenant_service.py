"""租户注册、凭据管理和 API Key 认证业务逻辑。"""

from datetime import datetime, timezone
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
    CallbackSecretCipher,
    api_key_matches,
    extract_api_key_prefix,
    generate_api_key,
    generate_callback_secret,
)


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""

    return datetime.now(timezone.utc)


class TenantService:
    """提供租户、API Key 和回调签名凭据的业务能力。"""

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
    ) -> tuple[TenantApiKey, str]:
        """为租户生成新的 API Key，明文只随本次调用返回。"""

        self.get_tenant(tenant_id, db)
        generated_key = generate_api_key()
        api_key = TenantApiKey(
            tenant_id=tenant_id,
            name=name.strip(),
            key_prefix=generated_key.key_prefix,
            key_hash=generated_key.key_hash,
            expires_at=expires_at,
        )
        self.repository.add_api_key(api_key, db)
        self._commit_or_conflict(db, "API Key 前缀冲突，请重试")
        db.refresh(api_key)
        return api_key, generated_key.plaintext

    def list_api_keys(self, tenant_id: UUID, db: Session) -> list[TenantApiKey]:
        """查询租户 API Key 元数据，不返回明文和哈希。"""

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

        key_prefix = extract_api_key_prefix(plaintext_api_key)
        if not key_prefix:
            raise InvalidApiKeyError("API Key 格式错误")

        api_key = self.repository.get_api_key_by_prefix(key_prefix, db)
        if not api_key or not api_key_matches(plaintext_api_key, api_key.key_hash):
            raise InvalidApiKeyError("API Key 无效")
        if api_key.status != "ACTIVE":
            raise InvalidApiKeyError("API Key 已停用或撤销")
        if api_key.expires_at and self._is_expired(api_key.expires_at):
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
        expires_at: datetime | None,
        db: Session,
    ) -> tuple[TenantCallbackCredential, str]:
        """创建回调 HMAC 凭据并加密保存密钥。"""

        self.get_tenant(tenant_id, db)
        key_id, secret = generate_callback_secret()
        try:
            cipher = CallbackSecretCipher.from_environment()
            secret_ciphertext = cipher.encrypt(secret)
        except ValueError as exc:
            raise CredentialConfigurationError(str(exc)) from exc

        credential = TenantCallbackCredential(
            tenant_id=tenant_id,
            name=name.strip(),
            key_id=key_id,
            secret_ciphertext=secret_ciphertext,
            expires_at=expires_at,
        )
        self.repository.add_callback_credential(credential, db)
        self._commit_or_conflict(db, "回调凭据 Key ID 冲突，请重试")
        db.refresh(credential)
        return credential, secret

    def list_callback_credentials(
        self,
        tenant_id: UUID,
        db: Session,
    ) -> list[TenantCallbackCredential]:
        """查询租户回调签名凭据元数据。"""

        self.get_tenant(tenant_id, db)
        return self.repository.list_callback_credentials(tenant_id, db)

    def revoke_callback_credential(
        self,
        tenant_id: UUID,
        credential_id: UUID,
        db: Session,
    ) -> TenantCallbackCredential:
        """撤销回调签名凭据。"""

        credential = self.repository.get_callback_credential_by_id(credential_id, db)
        if not credential or credential.tenant_id != tenant_id:
            raise CredentialNotFoundError("回调签名凭据不存在")
        if credential.status != "REVOKED":
            credential.status = "REVOKED"
            credential.revoked_at = utc_now()
            db.add(credential)
            db.commit()
            db.refresh(credential)
        return credential

    @staticmethod
    def _is_expired(expires_at: datetime) -> bool:
        """兼容数据库可能返回的无时区时间并判断是否过期。"""

        normalized_expiration = expires_at
        if normalized_expiration.tzinfo is None:
            normalized_expiration = normalized_expiration.replace(tzinfo=timezone.utc)
        return normalized_expiration <= utc_now()

    @staticmethod
    def _commit_or_conflict(db: Session, message: str) -> None:
        """提交事务，并将数据库唯一约束错误转换为领域冲突。"""

        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise TenantConflictError(message) from exc
