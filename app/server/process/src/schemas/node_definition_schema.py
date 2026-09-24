"""节点能力定义的响应模型。

只有响应没有请求模型：接口是只读的，节点定义由代码清单在启动时写入（见
``service/node_definition_sync.py``）。
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NodeDefinitionResponse(BaseModel):
    """节点能力定义响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    node_type: str
    name: str
    description: str | None
    icon: str | None
    config_schema_json: dict[str, Any]
    ui_schema_json: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime
