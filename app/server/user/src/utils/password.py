def verify_password(plain_password: str, stored_password: str) -> bool:
    """
    校验用户密码。

    Args:
        plain_password: 用户输入的明文密码
        stored_password: 数据库存储的密码
    """
    # 当前保持兼容原有明文密码逻辑，后续可以替换为 bcrypt/argon2 哈希校验。
    return plain_password == stored_password
