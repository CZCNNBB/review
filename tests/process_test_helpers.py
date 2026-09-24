"""审批流模块测试共用辅助：内置节点定义和数据库会话。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.common.db.postgres_db import engine
from app.server.process.src.constants import NODE_DEFINITION_STATUS_ENABLED
from app.server.process.src.node_catalog import NODE_TYPES
from app.server.process.src.service.node_definition_sync import sync_node_definitions


INITIALIZATION_SQL_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "init.sql"
)


@dataclass(frozen=True)
class BuiltinNodeDefinition:
    """代码清单里的一个内置节点类型，字段对应数据库里的节点定义行。"""

    id: UUID
    node_type: str
    name: str
    description: str
    icon: str
    config_schema_json: dict[str, Any]
    ui_schema_json: dict[str, Any]
    status: str


def load_builtin_node_definitions() -> dict[str, BuiltinNodeDefinition]:
    """按代码里的节点类型清单构造内置节点定义，按 node_type 建索引。

    清单的唯一真相在 ``src/node_catalog.py``（应用启动时会同步进数据库），测试读同一份，
    避免另写一份配置 Schema 而产生漂移。
    """

    return {
        node_type: BuiltinNodeDefinition(
            id=spec.id,
            node_type=node_type,
            name=spec.name,
            description=spec.description,
            icon=spec.icon,
            config_schema_json=spec.config_schema_json,
            ui_schema_json=spec.ui_schema_json,
            status=NODE_DEFINITION_STATUS_ENABLED,
        )
        for node_type, spec in NODE_TYPES.items()
    }


def ensure_builtin_node_definitions(session: Session) -> None:
    """把代码清单同步进测试库，保证内置定义行存在。

    节点定义不再由 init.sql seed（清单已经搬进代码），而版本节点外键指向这些定义行，
    所以建流程版本之前必须先把它们补齐。这与应用启动时做的是同一件事。
    """

    sync_node_definitions(session)


class DatabaseTestCaseMixin:
    """为需要真实 PostgreSQL 的测试提供会话和自动清理。

    只清理本测试显式登记过的记录，绝不按名称或范围批量删除，避免误伤已有数据。
    """

    engine = engine

    def open_session(self) -> Session:
        """创建测试使用的数据库会话，并保证内置节点定义已在库中。"""

        self._session = Session(self.engine)
        # 节点定义由代码清单在启动时同步（init.sql 不再 seed），而版本节点的外键指向
        # 这些定义行，所以测试也要先补齐 —— 否则只有"应用启动过"的库才能跑通。
        ensure_builtin_node_definitions(self._session)
        self._created_process_ids: list[UUID] = []
        self._created_node_definition_ids: list[UUID] = []
        self._created_person_ids: list[UUID] = []
        self._created_tenant_ids: list[UUID] = []
        self._created_business_action_ids: list[UUID] = []

        # 用例的会话必须关闭，否则连接会一直挂在全局连接池上。tearDown 只在 setUp
        # 成功时才会执行，用例自身的 tearDown 也可能在调用 close_session 之前抛出，
        # 因此这里再注册一次清理：addCleanup 在 setUp 失败时同样会执行。
        self.addCleanup(self.close_session)
        return self._session

    def close_session(self) -> None:
        """清理本测试创建的数据并关闭会话，重复调用不做任何事。"""

        session = getattr(self, "_session", None)
        if session is None:
            return

        # 先清空引用，保证 tearDown 和 addCleanup 两个入口只会真正执行一次。
        self._session = None
        try:
            self._delete_created_records(session)
        finally:
            session.close()

    def _delete_created_records(self, session: Session) -> None:
        """按依赖顺序分组删除本测试创建的数据。

        每组单独提交：某一组删除失败不能影响其余组的清理，否则测试数据会静默残留在
        开发库里。失败信息会汇总抛出，让残留问题在测试结果里直接暴露。
        """

        # 运行数据的删除顺序：先解除实例对活动节点的引用，再按依赖从深到浅删除。
        process_instance_ids = (
            "SELECT id FROM process.approval_instance WHERE process_id = ANY(:ids)"
        )
        cleanup_groups: list[tuple[str, str, dict[str, list[UUID]] | None]] = [
            # 租户侧数据先删除，避免删除租户后留下引用该租户的授权记录和使用记录。
            (
                "审批使用记录",
                "DELETE FROM tenant.process_usage_record WHERE tenant_id = ANY(:ids)",
                {"ids": self._created_tenant_ids},
            ),
            (
                "业务动作授权",
                "DELETE FROM tenant.business_action_binding "
                "WHERE tenant_id = ANY(:ids)",
                {"ids": self._created_tenant_ids},
            ),
            (
                "流程授权",
                "DELETE FROM tenant.process_binding WHERE tenant_id = ANY(:ids)",
                {"ids": self._created_tenant_ids},
            ),
            (
                "租户 API Key",
                "DELETE FROM tenant.tenant_api_key WHERE tenant_id = ANY(:ids)",
                {"ids": self._created_tenant_ids},
            ),
            (
                "租户回调凭据",
                "DELETE FROM tenant.tenant_callback_credential "
                "WHERE tenant_id = ANY(:ids)",
                {"ids": self._created_tenant_ids},
            ),
            (
                "租户",
                "DELETE FROM tenant.tenant WHERE id = ANY(:ids)",
                {"ids": self._created_tenant_ids},
            ),
            (
                "业务动作",
                "DELETE FROM integration.business_action WHERE id = ANY(:ids)",
                {"ids": self._created_business_action_ids},
            ),
            (
                "清空流程当前版本引用",
                "UPDATE process.approval_process SET current_version_id = NULL "
                "WHERE id = ANY(:ids)",
                {"ids": self._created_process_ids},
            ),
            (
                "清空实例当前节点引用",
                "UPDATE process.approval_instance SET current_node_execution_id = NULL "
                f"WHERE id IN ({process_instance_ids})",
                {"ids": self._created_process_ids},
            ),
            (
                # 执行记录外键指向审批实例，必须先于实例删除。
                "业务执行记录",
                "DELETE FROM process.business_execution_record "
                f"WHERE approval_instance_id IN ({process_instance_ids})",
                {"ids": self._created_process_ids},
            ),
            (
                "审批记录",
                "DELETE FROM process.approval_record "
                f"WHERE instance_id IN ({process_instance_ids})",
                {"ids": self._created_process_ids},
            ),
            (
                "审批任务",
                "DELETE FROM process.approval_task "
                f"WHERE instance_id IN ({process_instance_ids})",
                {"ids": self._created_process_ids},
            ),
            (
                "节点执行记录",
                "DELETE FROM process.approval_node_execution "
                f"WHERE instance_id IN ({process_instance_ids})",
                {"ids": self._created_process_ids},
            ),
            (
                "审批实例",
                "DELETE FROM process.approval_instance WHERE process_id = ANY(:ids)",
                {"ids": self._created_process_ids},
            ),
            (
                "流程版本节点",
                "DELETE FROM process.approval_process_version_node "
                "WHERE process_version_id IN ("
                "SELECT id FROM process.approval_process_version "
                "WHERE process_id = ANY(:ids))",
                {"ids": self._created_process_ids},
            ),
            (
                "流程版本",
                "DELETE FROM process.approval_process_version "
                "WHERE process_id = ANY(:ids)",
                {"ids": self._created_process_ids},
            ),
            (
                "流程主体",
                "DELETE FROM process.approval_process WHERE id = ANY(:ids)",
                {"ids": self._created_process_ids},
            ),
            (
                "节点能力定义",
                "DELETE FROM process.node_definition WHERE id = ANY(:ids)",
                {"ids": self._created_node_definition_ids},
            ),
            (
                "人员",
                "DELETE FROM organization.person WHERE id = ANY(:ids)",
                {"ids": self._created_person_ids},
            ),
        ]

        cleanup_failures: list[str] = []
        for label, statement, parameters in cleanup_groups:
            if not parameters or not parameters["ids"]:
                continue
            try:
                session.execute(text(statement), parameters)
                session.commit()
            except SQLAlchemyError as exc:
                session.rollback()
                cleanup_failures.append(f"{label}（{len(parameters['ids'])} 条）：{exc}")

        if cleanup_failures:
            raise AssertionError("测试数据清理失败，已在开发库留下残留：" + "；".join(cleanup_failures))

    def track_process(self, process_id: UUID) -> UUID:
        """登记测试创建的流程，供清理阶段定点删除。"""

        self._created_process_ids.append(process_id)
        return process_id

    def track_node_definition(self, node_definition_id: UUID) -> UUID:
        """登记测试创建的节点定义，供清理阶段定点删除。"""

        self._created_node_definition_ids.append(node_definition_id)
        return node_definition_id

    def track_person(self, person_id: UUID) -> UUID:
        """登记测试创建的人员，供清理阶段定点删除。"""

        self._created_person_ids.append(person_id)
        return person_id

    def track_tenant(self, tenant_id: UUID) -> UUID:
        """登记测试创建的租户，供清理阶段定点删除租户侧全部数据。"""

        self._created_tenant_ids.append(tenant_id)
        return tenant_id

    def track_business_action(self, business_action_id: UUID) -> UUID:
        """登记测试创建的业务动作，供清理阶段定点删除。"""

        self._created_business_action_ids.append(business_action_id)
        return business_action_id
