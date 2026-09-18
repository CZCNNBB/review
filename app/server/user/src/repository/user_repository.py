from sqlmodel import Session, select

from app.server.user.src.config.user_config import USER_ACTIVE_STATUS
from app.server.user.src.models.user_model import User


class UserRepository:
    """用户服务数据访问层。"""

    def get_active_user_by_email(self, email: str, db: Session):
        """
        按邮箱查询未删除用户。

        Args:
            email: 用户邮箱
            db: 数据库会话
        """
        # 只查询未删除用户，避免软删除账号继续参与登录或注册判断。
        sql = select(User).where(User.email == email, User.is_delete == USER_ACTIVE_STATUS)
        return db.exec(sql).first()

    def get_active_user_by_email_and_password(self, email: str, password: str, db: Session):
        """
        按邮箱和密码查询未删除用户。

        Args:
            email: 用户邮箱
            password: 用户密码
            db: 数据库会话
        """
        # 当前代码沿用原有明文密码匹配逻辑，后续可替换为 password utils 中的哈希校验。
        sql = select(User).where(
            User.email == email,
            User.password == password,
            User.is_delete == USER_ACTIVE_STATUS,
        )
        return db.exec(sql).first()

    def create_user(self, email: str, password: str, name: str, db: Session):
        """
        创建用户并提交事务。

        Args:
            email: 用户邮箱
            password: 用户密码
            name: 用户名
            db: 数据库会话
        """
        # 新用户默认标记为未删除状态。
        new_user = User(email=email, password=password, name=name, is_delete=USER_ACTIVE_STATUS)
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
