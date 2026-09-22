"""业务动作数据访问实现。"""

from uuid import UUID

from sqlmodel import Session, select

from app.server.integration.src.models.business_action_model import BusinessAction


class BusinessActionRepository:
    """封装业务动作表的数据库查询。"""

    def add(self, action: BusinessAction, db: Session) -> None:
        """将业务动作加入当前数据库事务。"""

        db.add(action)

    def get_by_id(self, action_id: UUID, db: Session) -> BusinessAction | None:
        """按主键查询业务动作。"""

        return db.get(BusinessAction, action_id)

    def get_by_code(self, action_code: str, db: Session) -> BusinessAction | None:
        """按稳定的业务动作标识查询动作。"""

        statement = select(BusinessAction).where(
            BusinessAction.action_code == action_code
        )
        return db.exec(statement).first()

    def list_actions(
        self,
        db: Session,
        status: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[BusinessAction]:
        """按创建时间倒序分页查询业务动作，可按状态筛选。"""

        statement = select(BusinessAction)
        if status:
            statement = statement.where(BusinessAction.status == status)
        statement = (
            statement.order_by(BusinessAction.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(db.exec(statement).all())
