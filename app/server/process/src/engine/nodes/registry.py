"""节点处理器注册表：node_type → 处理器。

清单（每种类型叫什么、有哪些配置项）在 ``src/node_catalog.py``；这里给它绑上"谁来跑"。
**新增一种节点类型 = 新建 ``nodes/<类型>.py`` 写一个处理器 + 在这里加一行 + 在清单里加一条**
（清单那步别忘：绑定时会校验两边一致，漏了会在启动时直接报错，不是等到运行期）。
"""

from app.server.process.src.constants import (
    NODE_TYPE_APPROVAL,
    NODE_TYPE_CONDITION,
    NODE_TYPE_END,
    NODE_TYPE_START,
)
from app.server.process.src.engine.nodes.approval import ApprovalNodeHandler
from app.server.process.src.engine.nodes.base import NodeHandler
from app.server.process.src.engine.nodes.condition import ConditionNodeHandler
from app.server.process.src.engine.nodes.end import EndNodeHandler
from app.server.process.src.engine.nodes.start import StartNodeHandler
from app.server.process.src.node_catalog import NODE_TYPES

# 处理器无状态，进程内各建一个实例即可。
NODE_HANDLERS: dict[str, NodeHandler] = {
    NODE_TYPE_START: StartNodeHandler(),
    NODE_TYPE_APPROVAL: ApprovalNodeHandler(),
    NODE_TYPE_CONDITION: ConditionNodeHandler(),
    NODE_TYPE_END: EndNodeHandler(),
}

# 清单与处理器必须一一对应：只有清单没有处理器 = 节点跑不起来；只有处理器没有清单 =
# 这个类型创建不出来、也发布不了。两边不一致时立刻报出来，别留到运行期才发现。
_missing_handlers = sorted(set(NODE_TYPES) - set(NODE_HANDLERS))
_missing_specs = sorted(set(NODE_HANDLERS) - set(NODE_TYPES))
if _missing_handlers or _missing_specs:
    raise RuntimeError(
        "节点类型清单与处理器注册表不一致："
        f"清单里有 {_missing_handlers or '无'} 缺处理器，"
        f"注册表里有 {_missing_specs or '无'} 缺清单。"
        "新增节点类型时，src/node_catalog.py 的 NODE_TYPES 与 "
        "engine/nodes/registry.py 的 NODE_HANDLERS 必须一起改。"
    )
