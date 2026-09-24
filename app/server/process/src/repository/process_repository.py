"""审批流主体、流程版本和版本节点数据访问实现。"""

from uuid import UUID

from sqlmodel import Session, func, select

from app.server.process.src.constants import (
    PROCESS_STATUS_ENABLED,
    PROCESS_VERSION_STATUS_DRAFT,
)
from app.server.process.src.models.process_model import (
    ApprovalProcess,
    ApprovalProcessVersion,
    ApprovalProcessVersionNode,
)


class ProcessRepository:
    """封装审批流、版本和版本节点的数据库查询。"""

    def add_process(self, process: ApprovalProcess, db: Session) -> None:
        """将审批流主体加入当前事务。"""

        db.add(process)

    def get_process_by_id(self, process_id: UUID, db: Session) -> ApprovalProcess | None:
        """按主键查询审批流主体。"""

        return db.get(ApprovalProcess, process_id)

    def get_process_for_update(
        self,
        process_id: UUID,
        db: Session,
    ) -> ApprovalProcess | None:
        """锁定并刷新流程主体，串行化草稿创建、发布和停用操作。"""

        statement = (
            select(ApprovalProcess)
            .where(ApprovalProcess.id == process_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return db.exec(statement).first()

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

    def add_version(self, version: ApprovalProcessVersion, db: Session) -> None:
        """将流程版本加入当前事务。"""

        db.add(version)

    def get_version_by_id(
        self,
        version_id: UUID,
        db: Session,
    ) -> ApprovalProcessVersion | None:
        """按主键查询流程版本。"""

        return db.get(ApprovalProcessVersion, version_id)

    def get_version_for_update(
        self,
        version_id: UUID,
        db: Session,
    ) -> ApprovalProcessVersion | None:
        """锁定并刷新流程版本，保证 revision 校验和发布原子执行。"""

        statement = (
            select(ApprovalProcessVersion)
            .where(ApprovalProcessVersion.id == version_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return db.exec(statement).first()

    def list_versions(
        self,
        process_id: UUID,
        db: Session,
    ) -> list[ApprovalProcessVersion]:
        """按版本号倒序查询一条流程的全部版本。"""

        statement = (
            select(ApprovalProcessVersion)
            .where(ApprovalProcessVersion.process_id == process_id)
            .order_by(ApprovalProcessVersion.version_no.desc())
        )
        return list(db.exec(statement).all())

    def get_draft_version(
        self,
        process_id: UUID,
        db: Session,
    ) -> ApprovalProcessVersion | None:
        """查询一条流程唯一的草稿版本。"""

        statement = select(ApprovalProcessVersion).where(
            ApprovalProcessVersion.process_id == process_id,
            ApprovalProcessVersion.status == PROCESS_VERSION_STATUS_DRAFT,
        )
        return db.exec(statement).first()

    def get_latest_version_no(self, process_id: UUID, db: Session) -> int:
        """查询流程当前最大版本号，没有版本时返回零。"""

        statement = select(func.max(ApprovalProcessVersion.version_no)).where(
            ApprovalProcessVersion.process_id == process_id
        )
        return int(db.exec(statement).one() or 0)

    def add_node(self, node: ApprovalProcessVersionNode, db: Session) -> None:
        """将版本节点加入当前事务。"""

        db.add(node)

    def delete_node(self, node: ApprovalProcessVersionNode, db: Session) -> None:
        """从当前事务删除草稿版本节点。"""

        db.delete(node)

    def list_nodes(
        self,
        version_id: UUID,
        db: Session,
    ) -> list[ApprovalProcessVersionNode]:
        """按创建时间和主键稳定排序查询版本的全部节点。"""

        statement = (
            select(ApprovalProcessVersionNode)
            .where(ApprovalProcessVersionNode.process_version_id == version_id)
            .order_by(
                ApprovalProcessVersionNode.created_at.asc(),
                ApprovalProcessVersionNode.id.asc(),
            )
        )
        return list(db.exec(statement).all())

    def list_nodes_by_ids(
        self,
        node_ids: list[UUID],
        db: Session,
    ) -> list[ApprovalProcessVersionNode]:
        """跨版本查询节点 ID，用于阻止前端节点 ID 覆盖其它版本。"""

        if not node_ids:
            return []
        statement = select(ApprovalProcessVersionNode).where(
            ApprovalProcessVersionNode.id.in_(node_ids)
        )
        return list(db.exec(statement).all())

    def count_nodes_by_version_ids(
        self,
        version_ids: list[UUID],
        db: Session,
    ) -> dict[UUID, int]:
        """批量统计多个版本的节点数量。"""

        if not version_ids:
            return {}
        statement = (
            select(ApprovalProcessVersionNode.process_version_id, func.count())
            .where(ApprovalProcessVersionNode.process_version_id.in_(version_ids))
            .group_by(ApprovalProcessVersionNode.process_version_id)
        )
        return {
            version_id: node_count
            for version_id, node_count in db.exec(statement).all()
        }
