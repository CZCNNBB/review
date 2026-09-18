from pydantic import BaseModel


class UserAuthResponse(BaseModel):
    """用户登录或注册成功后的响应数据。"""

    message: str
    id: int
    email: str
    name: str
