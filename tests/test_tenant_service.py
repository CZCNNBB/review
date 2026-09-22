"""租户模块关键凭据和隔离逻辑测试。"""

import os
import unittest

from cryptography.fernet import Fernet
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.server.tenant.src.models import Tenant, TenantApiKey, TenantCallbackCredential
from app.server.tenant.src.schemas.tenant_schema import TenantCreateRequest
from app.server.tenant.src.service.exceptions import (
    CredentialNotFoundError,
    InvalidApiKeyError,
    TenantConflictError,
)
from app.server.tenant.src.service.tenant_service import TenantService
from app.server.tenant.src.utils.credential import CallbackSecretCipher


class TenantServiceTestCase(unittest.TestCase):
    """验证租户创建、API Key 认证和回调密钥加密。"""

    def setUp(self) -> None:
        """创建每个测试独立使用的内存数据库。"""

        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            # SQLite 没有 PostgreSQL Schema，测试时将 tenant 映射到默认命名空间。
            execution_options={
                "schema_translate_map": {
                    "tenant": None,
                    "organization": None,
                    "process": None,
                    "integration": None,
                }
            },
        )
        SQLModel.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.service = TenantService()
        self.previous_master_key = os.environ.get("APPROVAL_CREDENTIAL_MASTER_KEY")
        os.environ["APPROVAL_CREDENTIAL_MASTER_KEY"] = Fernet.generate_key().decode("utf-8")

    def tearDown(self) -> None:
        """关闭数据库会话并恢复测试前环境变量。"""

        self.db.close()
        self.engine.dispose()
        if self.previous_master_key is None:
            os.environ.pop("APPROVAL_CREDENTIAL_MASTER_KEY", None)
        else:
            os.environ["APPROVAL_CREDENTIAL_MASTER_KEY"] = self.previous_master_key

    def create_tenant(self) -> Tenant:
        """创建测试使用的财务系统租户。"""

        request = TenantCreateRequest(
            code="finance",
            name="财务系统",
            callback_base_url="https://finance.example.com/internal/approval/",
        )
        return self.service.create_tenant(request, self.db)

    def test_api_key_can_authenticate_and_cannot_authenticate_after_revoke(self) -> None:
        """API Key 创建后可认证，撤销后必须立即失效。"""

        tenant = self.create_tenant()
        api_key = self.service.create_api_key(
            tenant_id=tenant.id,
            name="生产环境主 Key",
            expires_at=None,
            db=self.db,
        )

        authenticated_tenant, authenticated_key = self.service.authenticate_api_key(
            api_key.api_key,
            self.db,
        )
        self.assertEqual(authenticated_tenant.id, tenant.id)
        self.assertEqual(authenticated_key.id, api_key.id)
        self.assertIsNotNone(authenticated_key.last_used_at)

        self.service.revoke_api_key(tenant.id, api_key.id, self.db)
        with self.assertRaises(InvalidApiKeyError):
            self.service.authenticate_api_key(api_key.api_key, self.db)

    def test_duplicate_tenant_code_is_rejected_after_normalization(self) -> None:
        """大小写不同但含义相同的租户编码不能重复创建。"""

        self.create_tenant()
        duplicate_request = TenantCreateRequest(
            code="FINANCE",
            name="另一个财务系统",
            callback_base_url="https://finance-two.example.com/internal/approval",
        )

        with self.assertRaises(TenantConflictError):
            self.service.create_tenant(duplicate_request, self.db)

    def test_callback_secret_is_encrypted_and_can_be_decrypted(self) -> None:
        """回调密钥只以密文落库，并可由相同应用主密钥解密。"""

        tenant = self.create_tenant()
        credential, plaintext_secret = self.service.create_callback_credential(
            tenant_id=tenant.id,
            name="生产环境回调签名",
            expires_at=None,
            db=self.db,
        )

        self.assertNotEqual(credential.secret_ciphertext, plaintext_secret)
        cipher = CallbackSecretCipher.from_environment()
        self.assertEqual(cipher.decrypt(credential.secret_ciphertext), plaintext_secret)

    def test_cross_tenant_credential_revoke_is_rejected(self) -> None:
        """一个租户不能撤销另一个租户的 API Key。"""

        first_tenant = self.create_tenant()
        second_tenant = self.service.create_tenant(
            TenantCreateRequest(
                code="CONTRACT",
                name="合同系统",
                callback_base_url="https://contract.example.com/internal/approval",
            ),
            self.db,
        )
        api_key = self.service.create_api_key(
            tenant_id=first_tenant.id,
            name="主 Key",
            expires_at=None,
            db=self.db,
        )

        with self.assertRaises(CredentialNotFoundError):
            self.service.revoke_api_key(second_tenant.id, api_key.id, self.db)


if __name__ == "__main__":
    unittest.main()
