"""租户模块数据访问实现。"""

from uuid import UUID

from sqlmodel import Session, select

from app.server.tenant.src.models.tenant_model import (
    PersonBinding,
    Tenant,
    TenantApiKey,
    TenantCallbackCredential,
)


class TenantRepository:
    """封装租户及凭据表的数据库查询。"""

    def add_tenant(self, tenant: Tenant, db: Session) -> None:
        """将租户加入当前数据库事务。"""

        db.add(tenant)

    def get_tenant_by_id(self, tenant_id: UUID, db: Session) -> Tenant | None:
        """按主键查询租户。"""

        return db.get(Tenant, tenant_id)

    def get_tenant_by_code(self, code: str, db: Session) -> Tenant | None:
        """按租户编码查询租户。"""

        statement = select(Tenant).where(Tenant.code == code)
        return db.exec(statement).first()

    def list_tenants(self, db: Session, offset: int, limit: int) -> list[Tenant]:
        """按创建时间倒序分页查询租户。"""

        statement = select(Tenant).order_by(Tenant.created_at.desc()).offset(offset).limit(limit)
        return list(db.exec(statement).all())

    def add_api_key(self, api_key: TenantApiKey, db: Session) -> None:
        """将 API Key 元数据加入当前数据库事务。"""

        db.add(api_key)

    def get_api_key_by_id(self, api_key_id: UUID, db: Session) -> TenantApiKey | None:
        """按主键查询 API Key。"""

        return db.get(TenantApiKey, api_key_id)

    def get_api_key_by_value(self, api_key: str, db: Session) -> TenantApiKey | None:
        """按完整明文查询 API Key。"""

        statement = select(TenantApiKey).where(TenantApiKey.api_key == api_key)
        return db.exec(statement).first()

    def list_api_keys(self, tenant_id: UUID, db: Session) -> list[TenantApiKey]:
        """查询租户的全部 API Key 元数据。"""

        statement = (
            select(TenantApiKey)
            .where(TenantApiKey.tenant_id == tenant_id)
            .order_by(TenantApiKey.created_at.desc())
        )
        return list(db.exec(statement).all())

    def add_callback_credential(self, credential: TenantCallbackCredential, db: Session) -> None:
        """将回调签名凭据加入当前数据库事务。"""

        db.add(credential)

    def get_callback_credential_by_id(
        self,
        credential_id: UUID,
        db: Session,
    ) -> TenantCallbackCredential | None:
        """按主键查询回调签名凭据。"""

        return db.get(TenantCallbackCredential, credential_id)

    def list_callback_credentials(
        self,
        tenant_id: UUID,
        db: Session,
    ) -> list[TenantCallbackCredential]:
        """查询租户的全部回调凭据元数据。"""

        statement = (
            select(TenantCallbackCredential)
            .where(TenantCallbackCredential.tenant_id == tenant_id)
            .order_by(TenantCallbackCredential.created_at.desc())
        )
        return list(db.exec(statement).all())

    def get_active_callback_credential(
        self,
        tenant_id: UUID,
        db: Session,
    ) -> TenantCallbackCredential | None:
        """查询租户当前唯一有效的回调凭据。

        数据库的部分唯一索引保证同一租户最多只有一条 ACTIVE 记录，这里的查询顺序仅
        用于数据被手工修改后仍能稳定返回最新一条。
        """

        statement = (
            select(TenantCallbackCredential)
            .where(
                TenantCallbackCredential.tenant_id == tenant_id,
                TenantCallbackCredential.status == "ACTIVE",
            )
            .order_by(TenantCallbackCredential.created_at.desc())
        )
        return db.exec(statement).first()

    def get_person_binding(
        self,
        tenant_id: UUID,
        person_id: UUID,
        db: Session,
    ) -> PersonBinding | None:
        """查询租户与人员的绑定。"""

        statement = select(PersonBinding).where(
            PersonBinding.tenant_id == tenant_id,
            PersonBinding.person_id == person_id,
        )
        return db.exec(statement).first()

    def list_person_bindings(self, tenant_id: UUID, db: Session) -> list[PersonBinding]:
        """查询租户的全部人员绑定。"""

        statement = (
            select(PersonBinding)
            .where(PersonBinding.tenant_id == tenant_id)
            .order_by(PersonBinding.created_at.desc())
        )
        return list(db.exec(statement).all())
