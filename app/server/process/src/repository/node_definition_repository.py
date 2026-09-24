"""节点能力定义数据访问实现。"""

from uuid import UUID

from sqlalchemy import case
from sqlmodel import Session, select

from app.server.process.src.models.process_model import NodeDefinition
from app.server.process.src.node_catalog import NODE_TYPES

# 清单里的声明顺序就是列表顺序（开始 → 人工审批 → 条件分支 → 结束），画布的节点面板
# 和「节点定义」页都按这个顺序读。清单里没有的类型（历史遗留或已下线的）排在最后。
_ORDER_MAP = {node_type: index for index, node_type in enumerate(NODE_TYPES)}
_CATALOG_ORDER = case(_ORDER_MAP, value=NodeDefinition.node_type, else_=len(_ORDER_MAP))


class NodeDefinitionRepository:
    """封装节点能力定义表的数据库查询。"""

    def add(self, definition: NodeDefinition, db: Session) -> None:
        """将节点能力定义加入当前数据库事务。"""

        db.add(definition)

    def get_by_id(self, node_definition_id: UUID, db: Session) -> NodeDefinition | None:
        """按主键查询节点能力定义。"""

        return db.get(NodeDefinition, node_definition_id)

    def get_by_name(self, name: str, db: Session) -> NodeDefinition | None:
        """按名称查询节点能力定义，用于重名判断。"""

        statement = select(NodeDefinition).where(NodeDefinition.name == name)
        return db.exec(statement).first()

    def list_definitions(
        self,
        db: Session,
        offset: int,
        limit: int,
    ) -> list[NodeDefinition]:
        """按清单顺序分页查询节点能力定义，同一类型内新行在前。"""

        statement = (
            select(NodeDefinition)
            .order_by(_CATALOG_ORDER, NodeDefinition.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(db.exec(statement).all())

    def list_by_ids(
        self,
        node_definition_ids: list[UUID],
        db: Session,
    ) -> list[NodeDefinition]:
        """批量按主键查询节点能力定义，供流程校验一次性取回引用数据。"""

        if not node_definition_ids:
            return []

        statement = select(NodeDefinition).where(
            NodeDefinition.id.in_(node_definition_ids)
        )
        return list(db.exec(statement).all())
