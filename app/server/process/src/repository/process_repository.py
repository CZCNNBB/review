"""审批流定义和流程节点实例数据访问实现。"""

from uuid import UUID

from sqlmodel import Session, func, select

from app.server.process.src.constants import PROCESS_STATUS_ENABLED
from app.server.process.src.models.process_model import (
    ApprovalProcess,
    ApprovalProcessNode,
)


class ProcessRepository:
    """封装审批流主体和流程节点实例的数据库查询。"""

    def add_process(self, process: ApprovalProcess, db: Session) -> None:
        """将审批流主体加入当前数据库事务。"""

        db.add(process)

    def get_process_by_id(self, process_id: UUID, db: Session) -> ApprovalProcess | None:
        """按主键查询审批流主体。"""

        return db.get(ApprovalProcess, process_id)

    def list_processes(
        self,
        db: Session,
        offset: int,
        limit: int,
    ) -> list[ApprovalProcess]:
        """按更新时间倒序分页查询审批流。"""

        statement = (
            select(ApprovalProcess)
            .order_by(ApprovalProcess.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(db.exec(statement).all())

    def count_nodes_by_process_ids(
        self,
        process_ids: list[UUID],
        db: Session,
    ) -> dict[UUID, int]:
        """批量统计每条流程的节点数量，避免列表查询出现 N+1。"""

        if not process_ids:
            return {}

        statement = (
            select(ApprovalProcessNode.process_id, func.count())
            .where(ApprovalProcessNode.process_id.in_(process_ids))
            .group_by(ApprovalProcessNode.process_id)
        )
        return {
            process_id: node_count
            for process_id, node_count in db.exec(statement).all()
        }

    def add_node(self, node: ApprovalProcessNode, db: Session) -> None:
        """将流程节点实例加入当前数据库事务。"""

        db.add(node)

    def delete_node(self, node: ApprovalProcessNode, db: Session) -> None:
        """在当前数据库事务中删除流程节点实例。"""

        db.delete(node)

    def list_nodes(self, process_id: UUID, db: Session) -> list[ApprovalProcessNode]:
        """按创建时间正序查询一条流程的全部节点实例。"""

        statement = (
            select(ApprovalProcessNode)
            .where(ApprovalProcessNode.process_id == process_id)
            .order_by(ApprovalProcessNode.created_at.asc(), ApprovalProcessNode.id.asc())
        )
        return list(db.exec(statement).all())

    def list_nodes_by_ids(
        self,
        node_ids: list[UUID],
        db: Session,
    ) -> list[ApprovalProcessNode]:
        """批量按主键查询节点实例。

        这里有意不按 process_id 过滤：保存流程时需要确认前端提交的节点 ID 没有被
        其它流程占用，否则平凡更新会覆盖掉别人的节点数据。
        """

        if not node_ids:
            return []

        statement = select(ApprovalProcessNode).where(
            ApprovalProcessNode.id.in_(node_ids)
        )
        return list(db.exec(statement).all())

    def has_enabled_process_reference(
        self,
        node_definition_id: UUID,
        db: Session,
    ) -> bool:
        """判断节点定义是否已经被任意已启用流程引用。

        这里只读取一条主键即可，不加载完整流程和节点，避免节点定义更新时产生
        不必要的数据读取。
        """

        statement = (
            select(ApprovalProcessNode.id)
            .join(
                ApprovalProcess,
                ApprovalProcess.id == ApprovalProcessNode.process_id,
            )
            .where(
                ApprovalProcessNode.node_definition_id == node_definition_id,
                ApprovalProcess.status == PROCESS_STATUS_ENABLED,
            )
            .limit(1)
        )
        return db.exec(statement).first() is not None
