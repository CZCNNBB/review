from typing import Any

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.common.schemas.result import Result
from app.server.user.src.schemas.request import LoginRequest, RegisterRequest
from app.server.user.src.service.user_service import UserService


router = APIRouter()

# 创建服务实例，接口层只负责调用服务，不直接写业务逻辑。
user_service = UserService()


@router.post("/login", response_model=Result[Any], summary="用户登录")
def login(login_request: LoginRequest, postgres_db: Session = Depends(get_postgres_engine)):
    """
    用户登录接口。

    Args:
        login_request: 用户登录请求参数
        postgres_db: PostgreSQL 数据库会话
    """
    try:
        user = user_service.login(login_request.email, login_request.password, postgres_db)
        if user:
            return Result.success(user)
        return Result.fail(401, "登录失败")
    except Exception as e:
        return Result.fail(401, f"登录失败: {str(e)}")


@router.post("/register", response_model=Result[Any], summary="用户注册")
def register(register_request: RegisterRequest, postgres_db: Session = Depends(get_postgres_engine)):
    """
    用户注册接口。

    Args:
        register_request: 用户注册请求参数
        postgres_db: PostgreSQL 数据库会话
    """
    try:
        user = user_service.register(
            register_request.email,
            register_request.password,
            register_request.name,
            postgres_db,
        )
        if user:
            return Result.success(user)
        return Result.fail(400, "注册失败")
    except Exception as e:
        return Result.fail(400, f"注册失败: {str(e)}")
