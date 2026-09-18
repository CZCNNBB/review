from pydantic import BaseModel


class LoginRequest(BaseModel):
    """用户登录请求参数。"""

    email: str
    password: str


class RegisterRequest(BaseModel):
    """用户注册请求参数。"""

    email: str
    password: str
    name: str
