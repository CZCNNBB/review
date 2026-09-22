"""API Key 生成、Service Token 加密和凭据过期判断工具。"""

import os
import secrets
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken


API_KEY_PREFIX = "appr_live"


def generate_api_key() -> str:
    """生成业务系统调用审批中心时使用的高熵 API Key。"""

    key_prefix = secrets.token_hex(4)
    secret = secrets.token_urlsafe(32)
    return f"{API_KEY_PREFIX}_{key_prefix}.{secret}"


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""

    return datetime.now(timezone.utc)


def is_expired(expires_at: datetime | None) -> bool:
    """兼容数据库可能返回的无时区时间并判断凭据是否过期。

    没有设置过期时间的凭据永远有效。
    """

    if expires_at is None:
        return False

    normalized_expiration = expires_at
    if normalized_expiration.tzinfo is None:
        normalized_expiration = normalized_expiration.replace(tzinfo=timezone.utc)
    return normalized_expiration <= utc_now()


class CredentialCipher:
    """使用应用主密钥加密和解密业务系统提供的 Service Token。

    回调时审批中心需要把 Token 原样发回业务系统，因此只能加密保存，不能只保存哈希。
    """

    def __init__(self, master_key: str):
        """初始化密钥加密器并校验主密钥格式。"""

        try:
            # Fernet 构造过程会校验主密钥是否为 URL-safe Base64 编码的 32 字节值。
            self._fernet = Fernet(master_key.encode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise ValueError("APPROVAL_CREDENTIAL_MASTER_KEY 格式无效") from exc

    @classmethod
    def from_environment(cls) -> "CredentialCipher":
        """从环境变量创建加密器，未配置时给出明确错误。"""

        master_key = os.getenv("APPROVAL_CREDENTIAL_MASTER_KEY")
        if not master_key:
            raise ValueError("未配置 APPROVAL_CREDENTIAL_MASTER_KEY")
        return cls(master_key)

    @staticmethod
    def generate_master_key() -> str:
        """生成可放入环境变量的 Fernet 主密钥。"""

        return Fernet.generate_key().decode("utf-8")

    def encrypt(self, plaintext: str) -> str:
        """加密业务系统提供的 Service Token。"""

        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """解密 Service Token，密文无效时抛出明确错误。"""

        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Service Token 无法解密") from exc
