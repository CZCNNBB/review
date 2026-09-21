"""审批流模块测试共用辅助：读取 seed 节点定义和准备数据库会话。"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.common.db.postgres_db import engine


INITIALIZATION_SQL_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "init.sql"
)

# 匹配 seed 语句里的单条 VALUES 记录。
_SEED_VALUE_PATTERN = re.compile(
    r"\(\s*"
    r"'([0-9a-fA-F-]{36})',\s*"
    r"'([A-Z]+)',\s*"
    r"'([^']*)',\s*"
    r"'([^']*)',\s*"
    r"'([^']*)',\s*"
    r"'(.*?)',\s*"
    r"'(.*?)',\s*"
    r"'(ENABLED|DISABLED)'",
    re.DOTALL,
)


@dataclass(frozen=True)
class SeedNodeDefinition:
    """从 init.sql 解析出的节点能力定义。"""

    id: UUID
    node_type: str
    name: str
    config_schema_json: dict[str, Any]
    ui_schema_json: dict[str, Any]
    status: str


def load_seed_node_definitions() -> dict[str, SeedNodeDefinition]:
    """解析 init.sql 中的 seed 节点定义，按 node_type 建索引。

    测试直接使用生产环境真正注册的配置 Schema，避免测试里另写一份而产生漂移。
    """

    sql_content = INITIALIZATION_SQL_PATH.read_text(encoding="utf-8")
    seed_statement = None
    for statement in sql_content.split(";"):
        if "INSERT INTO process.node_definition" in statement:
            seed_statement = statement
            break

    if seed_statement is None:
        raise AssertionError("init.sql 中缺少 process.node_definition 的 seed 语句")

    definitions: dict[str, SeedNodeDefinition] = {}
    for match in _SEED_VALUE_PATTERN.finditer(seed_statement):
        node_type = match.group(2)
        definitions[node_type] = SeedNodeDefinition(
            id=UUID(match.group(1)),
            node_type=node_type,
            name=match.group(3),
            config_schema_json=json.loads(match.group(6)),
            ui_schema_json=json.loads(match.group(7)),
            status=match.group(8),
        )

    if not definitions:
        raise AssertionError("init.sql 的 seed 语句没有解析出任何节点定义")

    return definitions


class DatabaseTestCaseMixin:
    """为需要真实 PostgreSQL 的测试提供会话和自动清理。

    只清理本测试显式登记过的记录，绝不按名称或范围批量删除，避免误伤已有数据。
    """

    engine = engine

    def open_session(self) -> Session:
        """创建测试使用的数据库会话。"""

        self._session = Session(self.engine)
        self._created_process_ids: list[UUID] = []
        self._created_node_definition_ids: list[UUID] = []
        self._created_person_ids: list[UUID] = []
        return self._session

    def close_session(self) -> None:
        """清理本测试创建的数据并关闭会话。"""

        session = getattr(self, "_session", None)
        if session is None:
            return

        try:
            self._delete_created_records(session)
        finally:
            session.close()

    def _delete_created_records(self, session: Session) -> None:
        """按依赖顺序分组删除本测试创建的数据。

        每组单独提交：某一组删除失败不能影响其余组的清理，否则测试数据会静默残留在
        开发库里。失败信息会汇总抛出，让残留问题在测试结果里直接暴露。
        """

        cleanup_groups: list[tuple[str, str, dict[str, list[UUID]] | None]] = [
            (
                "清空流程当前版本引用",
                "UPDATE process.approval_process SET current_version_id = NULL "
                "WHERE id = ANY(:ids)",
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
