"""与具体业务模块无关的临时管理接口认证。"""

import hmac
import os

from fastapi import Header, HTTPException, status


def verify_admin_key(x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")) -> None:
    """校验临时管理密钥，后续替换为项目平台管理员身份。"""

    expected_admin_key = os.getenv("APPROVAL_ADMIN_KEY")
    if not expected_admin_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="未配置 APPROVAL_ADMIN_KEY，管理接口不可用",
        )
    if not x_admin_key or not hmac.compare_digest(x_admin_key, expected_admin_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="管理密钥无效")

