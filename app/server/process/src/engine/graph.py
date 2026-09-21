"""运行期使用的流程版本视图。

已发布版本是不可变的，因此运行层可以一次读出节点和出边后反复使用。这里复用定义
模块的连线解析逻辑，避免运行期和校验期对编排结构的理解出现偏差。
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping, Sequence
from uuid import UUID

from app.server.process.src.constants import NODE_TYPE_START
from app.server.process.src.models.process_model import (
    ApprovalProcessVersion,
    ApprovalProcessVersionNode,
)
from app.server.process.src.service.exceptions import ProcessStateError
from app.server.process.src.service.process_validation import (
    GraphConnection,
    collect_form_fields,
    parse_connections,
)


@dataclass(frozen=True)
class VersionGraph:
    """一个已发布版本的节点索引、出边索引和表单字段格式。"""

    version: ApprovalProcessVersion
    nodes: Mapping[UUID, ApprovalProcessVersionNode]
    connections_by_source: Mapping[UUID, tuple[GraphConnection, ...]]
    start_node_id: UUID
    # 条件字段声明的 format，日期时间字段需要据此解析后再比较。
    field_formats: Mapping[str, str | None]

    def get_node(self, node_id: UUID) -> ApprovalProcessVersionNode | None:
        """按节点 ID 取回版本节点。"""

        return self.nodes.get(node_id)

    def outgoing(self, node_id: UUID) -> tuple[GraphConnection, ...]:
        """取回节点的全部出边，顺序与编排数组一致。"""

        return self.connections_by_source.get(node_id, ())


def build_version_graph(
    version: ApprovalProcessVersion,
    nodes: Sequence[ApprovalProcessVersionNode],
) -> VersionGraph:
    """把已发布版本组装成运行期视图。

    编排结构损坏或缺少唯一开始节点说明版本数据不可信，此时抛出状态异常让调用方
    终止本次推进，而不是让审批停在无法解释的位置。
    """

    connections, issues = parse_connections(version.orchestration_json)
    if issues:
        raise ProcessStateError("流程版本的编排数据不完整，无法推进审批")

    nodes_by_id = {node.id: node for node in nodes}
    connections_by_source: dict[UUID, list[GraphConnection]] = defaultdict(list)
    for connection in connections:
        connections_by_source[connection.source_node_id].append(connection)

    start_nodes = [
        node for node in nodes if node.node_type == NODE_TYPE_START
    ]
    if len(start_nodes) != 1:
        raise ProcessStateError("流程版本必须且只能包含一个开始节点，无法发起审批")

    return VersionGraph(
        version=version,
        nodes=nodes_by_id,
        connections_by_source={
            node_id: tuple(source_connections)
            for node_id, source_connections in connections_by_source.items()
        },
        start_node_id=start_nodes[0].id,
        field_formats={
            field_path: field_info.string_format
            for field_path, field_info in collect_form_fields(
                version.form_schema_json
            ).items()
        },
    )
