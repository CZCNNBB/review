"""API Key 生成和回调密钥加密工具。"""

import os
import secrets

from cryptography.fernet import Fernet, InvalidToken


API_KEY_PREFIX = "appr_live"


def generate_api_key() -> str:
    """生成业务系统调用审批中心时使用的高熵 API Key。"""

    key_prefix = secrets.token_hex(4)
    secret = secrets.token_urlsafe(32)
    return f"{API_KEY_PREFIX}_{key_prefix}.{secret}"


def generate_callback_secret() -> tuple[str, str]:
    """生成回调签名使用的 key_id 和高熵共享密钥。"""

    key_id = f"callback_{secrets.token_hex(6)}"
    secret = f"cbsec_{secrets.token_urlsafe(32)}"
    return key_id, secret


class CallbackSecretCipher:
    """使用应用主密钥加密和解密回调签名密钥。"""

    def __init__(self, master_key: str):
        """初始化密钥加密器并校验主密钥格式。"""

        try:
            # Fernet 构造过程会校验主密钥是否为 URL-safe Base64 编码的 32 字节值。
            self._fernet = Fernet(master_key.encode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise ValueError("APPROVAL_CREDENTIAL_MASTER_KEY 格式无效") from exc

    @classmethod
    def from_environment(cls) -> "CallbackSecretCipher":
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
        """加密回调签名密钥。"""

        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """解密回调签名密钥，密文无效时抛出明确错误。"""

        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("回调签名密钥无法解密") from exc
