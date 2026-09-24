"""节点类型的声明清单：每种类型叫什么、什么图标、有哪些配置项。

**这里是节点类型的唯一真相**，白名单 ``SUPPORTED_NODE_TYPES`` 由它派生；处理器在
``engine/nodes/registry.py`` 里按同样的键绑上去，两边不一致会在 import 时直接报错。
数据库里的 ``process.node_definition`` 只是应用启动时按这张表写入的副本，供画布和校验读取。

刻意做成**不依赖任何应用模块的叶子模块**（只用 constants 里的类型名）：
接口 schema 与流程校验都要读白名单，而它们处在依赖链的中间，这里一旦引用了引擎或模型，
就会成环。声明与执行分开也更好读 —— 这张表回答"有哪些节点"，引擎回答"怎么跑"。
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.server.process.src.constants import (
    NODE_TYPE_APPROVAL,
    NODE_TYPE_CONDITION,
    NODE_TYPE_END,
    NODE_TYPE_START,
)


@dataclass(frozen=True)
class NodeTypeSpec:
    """一种节点类型对外的样子（不含行为，行为由处理器负责）。

    ``id`` 是库里那一行节点定义的固定主键：写死是为了让联调库、测试库、老 demo 页面
    引用的是同一个 id，换环境不会对不上。新增类型时自己随便挑一个 UUID 定下来即可
    （只需要唯一，不需要有含义），改动它等于换了身份，已经引用旧 id 的版本节点会落空。
    """

    id: UUID
    name: str
    description: str
    icon: str
    config_schema_json: dict[str, Any]
    ui_schema_json: dict[str, Any]


NODE_TYPES: dict[str, NodeTypeSpec] = {
    NODE_TYPE_START: NodeTypeSpec(
        id=UUID("00000000-0000-0000-0000-000000000101"),
        name="开始",
        description="流程入口节点，每条流程必须且只能有一个开始节点",
        icon="play-circle",
        config_schema_json={
            "type": "object",
            "title": "开始",
            "additionalProperties": False,
            "properties": {},
        },
        ui_schema_json={"ui:order": []},
    ),
    NODE_TYPE_APPROVAL: NodeTypeSpec(
        id=UUID("00000000-0000-0000-0000-000000000102"),
        name="人工审批",
        description=(
            "人工审批节点，配置审批模式和审批人，进入节点时同时为全部审批人创建待办任务"
        ),
        icon="user-check",
        config_schema_json={
            "type": "object",
            "title": "人工审批",
            "additionalProperties": False,
            "required": ["approval_mode", "approvers"],
            "properties": {
                "approval_mode": {
                    "type": "string",
                    "title": "审批模式",
                    "description": "AND 表示所有人同意后通过，OR 表示任意一人同意即通过",
                    "enum": ["AND", "OR"],
                },
                "approvers": {
                    "type": "array",
                    "title": "审批人",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["person_id"],
                        "properties": {
                            "person_id": {
                                "type": "string",
                                "format": "uuid",
                                "title": "人员 ID",
                            }
                        },
                    },
                },
            },
        },
        ui_schema_json={
            "approval_mode": {"ui:widget": "select"},
            "approvers": {"ui:widget": "person-select"},
        },
    ),
    NODE_TYPE_CONDITION: NodeTypeSpec(
        id=UUID("00000000-0000-0000-0000-000000000104"),
        name="条件分支",
        description=(
            "按审批表单里的字段判断走哪条路，本身不产生审批任务。"
            "分支条件和去向在节点的分支编辑器里配置，进入后立即选路。"
        ),
        icon="git-branch",
        config_schema_json={
            "type": "object",
            "title": "条件分支",
            "additionalProperties": False,
            "properties": {},
        },
        ui_schema_json={"ui:order": []},
    ),
    NODE_TYPE_END: NodeTypeSpec(
        id=UUID("00000000-0000-0000-0000-000000000103"),
        name="结束",
        description=(
            "流程正常的最终出口，走到这里就是审批通过、流程完成，节点本身没有配置项。"
            "审批被拒绝时实例在人工审批节点当场结束，不会走到结束节点。"
        ),
        icon="flag",
        config_schema_json={
            "type": "object",
            "title": "结束",
            "additionalProperties": False,
            "properties": {},
        },
        ui_schema_json={"ui:order": []},
    ),
}

# 后端已经实现的节点类型：流程校验用它判断版本节点里的 node_type 还能不能跑。
SUPPORTED_NODE_TYPES = frozenset(NODE_TYPES)
