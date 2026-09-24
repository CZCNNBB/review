"""把代码里的节点类型清单同步到数据库的节点定义行。

节点类型是代码的事：行为在 ``engine/nodes/``，声明（名字、图标、配置 Schema）在
``src/node_catalog.py``。数据库里的 ``process.node_definition`` 只是给画布和校验读的**副本**，
应用启动时按清单写入，保证库里的行与代码一致：

- 清单里的类型：认它那一行（按清单里的固定 id，没有就按 ``node_type``）就地更新，
  不换 id —— 版本节点引用着它；库里完全找不到的类型按固定 id 新建；
- 同一类型多出来的行（手工建的或历史遗留的）：**停用**，一类只留一种形态；
- 清单里没有的类型：**停用**，不删除（历史流程还引用着这些定义）；
- 有人手工改过库里的定义：会被改回来（这正是"收回所有权"的意思）。

不会影响正在跑的流程：版本节点在保存/发布时就固化了自己的 ``node_type`` 与配置，
运行期不读这张表；配置 Schema 变化只影响之后保存/发布的校验。
"""

import logging
from copy import deepcopy
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.common.db.postgres_db import get_db_session
from app.server.process.src.constants import (
    NODE_DEFINITION_STATUS_DISABLED,
    NODE_DEFINITION_STATUS_ENABLED,
)
from app.server.process.src.models.process_model import NodeDefinition, utc_now
from app.server.process.src.node_catalog import NODE_TYPES, NodeTypeSpec
from app.server.process.src.repository.node_definition_repository import (
    NodeDefinitionRepository,
)

logger = logging.getLogger(__name__)

# 定义表里就几条内置类型，一次列全够用；真有几百条时再谈分页。
_LIST_LIMIT = 1000


def pick_definition_rows(
    node_type: str,
    spec: NodeTypeSpec,
    rows: list[NodeDefinition],
) -> tuple[NodeDefinition, list[NodeDefinition]]:
    """挑出这一类型要保留的那一行，以及要停用的其余同类型行。

    正主是清单里那个固定 id；库里没有它时沿用最早那行的 id（版本节点可能引用着它），
    一行都没有就按清单 id 造一个待写入的新行。单独放出来是为了不起数据库就能测这段挑选。

    ``rows`` 必须按创建时间从早到晚排好。
    """

    primary = next((row for row in rows if row.id == spec.id), None)
    if primary is None:
        primary = rows[0] if rows else NodeDefinition(id=spec.id, node_type=node_type)
    return primary, [row for row in rows if row is not primary]


def sync_node_definitions(db: Session, repository: NodeDefinitionRepository | None = None) -> None:
    """按代码清单更新节点定义行，调用方负责提交事务。"""

    definitions = (repository or NodeDefinitionRepository()).list_definitions(
        db,
        offset=0,
        limit=_LIST_LIMIT,
    )

    rows_by_type: dict[str, list[NodeDefinition]] = {}
    for definition in definitions:
        rows_by_type.setdefault(definition.node_type, []).append(definition)
    # 同一类型有多行时留哪一行必须确定：统一按创建时间从早到晚，保留最早那条
    for rows in rows_by_type.values():
        rows.sort(key=lambda definition: definition.created_at)

    now = utc_now()
    for node_type, spec in NODE_TYPES.items():
        rows = rows_by_type.pop(node_type, [])
        # 一种类型只留一行：正主是清单里那个固定 id，库里多出来的行（手工建的、
        # 历史遗留的）一律停用 —— 节点类型跟着代码走，一类只有一种形态。
        primary, extras = pick_definition_rows(node_type, spec, rows)
        primary.name = spec.name
        primary.description = spec.description
        primary.icon = spec.icon
        primary.config_schema_json = deepcopy(spec.config_schema_json)
        primary.ui_schema_json = deepcopy(spec.ui_schema_json)
        primary.status = NODE_DEFINITION_STATUS_ENABLED
        primary.updated_at = now
        db.add(primary)

        for row in extras:
            _disable(row, now, reason=f"同类型只保留清单里那一行（{primary.name}）")
        if not rows:
            logger.info("节点类型 %s 在代码清单里，但库里还没有定义行，已新建", node_type)

    # 清单里已经没有的类型：停用而不是删除，历史流程的版本节点还引用着
    for node_type, rows in rows_by_type.items():
        for definition in rows:
            _disable(definition, now, reason="代码里已经没有这个节点类型")

    try:
        db.commit()
    except IntegrityError:
        # 名称或 id 撞了唯一约束：多是代码改了名、库里旧名还被占着，也可能是另一个进程
        # 同时启动抢先写入。都不是致命问题：本次不写即可，别让应用起不来。
        db.rollback()
        logger.exception("节点定义同步失败：与库里已有定义冲突，本次跳过")


def _disable(definition: NodeDefinition, now: datetime, reason: str) -> None:
    """停用一条定义，状态没变时不写库也不打日志。"""

    if definition.status == NODE_DEFINITION_STATUS_DISABLED:
        return
    definition.status = NODE_DEFINITION_STATUS_DISABLED
    definition.updated_at = now
    logger.warning("停用节点定义「%s」（%s）：%s", definition.name, definition.node_type, reason)


def sync_node_definitions_on_startup() -> None:
    """启动时同步一次：失败只记日志，不阻止应用启动。

    这是个"让数据与代码对齐"的维护动作，不是启动前提：数据库暂时连不上、或建库脚本
    还没跑过，都不该让整个服务起不来。
    """

    try:
        with get_db_session() as db:
            sync_node_definitions(db)
    except Exception:  # noqa: BLE001 - 启动阶段的兜底：任何异常都不该拦住服务启动
        logger.exception("节点定义同步失败，本次跳过；接口仍可正常服务")
    else:
        # 成功也留一行：不然"没看到失败"和"没跑起来"分不清
        logger.info("节点定义同步完成：%s 种节点类型已与代码清单一致", len(NODE_TYPES))
