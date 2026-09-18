from sqlmodel import Session

from app.server.user.src.repository.user_repository import UserRepository


class UserService:
    """用户服务业务逻辑层。"""

    def __init__(self, user_repository: UserRepository | None = None):
        """
        初始化用户服务。

        Args:
            user_repository: 用户数据访问对象，默认创建 UserRepository
        """
        # 通过构造函数注入 repository，方便后续测试或替换数据访问实现。
        self.user_repository = user_repository or UserRepository()

    def login(self, email: str, password: str, postgres_db: Session):
        """
        用户登录。

        Args:
            email: 邮箱
            password: 密码
            postgres_db: PostgreSQL 数据库会话
        """
        # 登录逻辑只关心业务判断，具体 SQL 查询交给 repository 层。
        user = self.user_repository.get_active_user_by_email_and_password(email, password, postgres_db)
        if not user:
            return {"error": "邮箱或密码错误"}

        return {
            "message": "登录成功",
            "id": user.id,
            "email": user.email,
            "name": user.name,
        }

    def register(self, email: str, password: str, name: str, postgres_db: Session):
        """
        用户注册。

        Args:
            email: 邮箱
            password: 密码
            name: 姓名
            postgres_db: PostgreSQL 数据库会话
        """
        # 注册前先检查同邮箱未删除用户，避免唯一索引冲突和重复账号。
        existing_user = self.user_repository.get_active_user_by_email(email, postgres_db)
        if existing_user:
            return {"error": "用户已存在"}

        new_user = self.user_repository.create_user(email, password, name, postgres_db)
        return {
            "message": "注册成功",
            "id": new_user.id,
            "email": new_user.email,
            "name": new_user.name,
        }
