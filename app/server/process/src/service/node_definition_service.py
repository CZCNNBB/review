"""节点能力定义业务逻辑。"""

from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.server.process.src.models.process_model import NodeDefinition
from app.server.process.src.repository.node_definition_repository import (
    NodeDefinitionRepository,
)
from app.server.process.src.repository.process_repository import ProcessRepository
from app.server.process.src.schemas.node_definition_schema import (
    NodeDefinitionCreateRequest,
    NodeDefinitionUpdateRequest,
)
from app.server.process.src.service.exceptions import (
    NodeDefinitionNotFoundError,
    ProcessConflictError,
)


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""

    return datetime.now(timezone.utc)


class NodeDefinitionService:
    """提供节点能力定义的查询和维护能力。"""

    def __init__(
        self,
        repository: NodeDefinitionRepository | None = None,
        process_repository: ProcessRepository | None = None,
    ):
        """初始化节点能力定义服务并允许测试注入 Repository。"""

        self.repository = repository or NodeDefinitionRepository()
        self.process_repository = process_repository or ProcessRepository()

    def create_definition(
        self,
        request: NodeDefinitionCreateRequest,
        db: Session,
    ) -> NodeDefinition:
        """创建节点能力定义。"""

        existing_definition = self.repository.get_by_name(request.name, db)
        if existing_definition:
            raise ProcessConflictError(f"节点定义名称 {request.name} 已存在")

        definition = NodeDefinition(
            node_type=request.node_type,
            name=request.name,
            description=request.description,
            icon=request.icon,
            config_schema_json=deepcopy(request.config_schema_json),
            ui_schema_json=deepcopy(request.ui_schema_json),
            status=request.status,
        )
        self.repository.add(definition, db)
        self._commit_or_conflict(db, "节点定义名称已存在")
        db.refresh(definition)
        return definition

    def list_definitions(
        self,
        db: Session,
        offset: int = 0,
        limit: int = 100,
    ) -> list[NodeDefinition]:
        """分页查询节点能力定义。"""

        return self.repository.list_definitions(db, offset=offset, limit=limit)

    def get_definition(
        self,
        node_definition_id: UUID,
        db: Session,
    ) -> NodeDefinition:
        """查询节点能力定义，不存在时抛出领域异常。"""

        definition = self.repository.get_by_id(node_definition_id, db)
        if not definition:
            raise NodeDefinitionNotFoundError("节点定义不存在")
        return definition

    def update_definition(
        self,
        node_definition_id: UUID,
        request: NodeDefinitionUpdateRequest,
        db: Session,
    ) -> NodeDefinition:
        """更新节点能力定义的名称、说明、图标、配置 Schema 或状态。"""

        definition = self.get_definition(node_definition_id, db)

        self._ensure_runtime_contract_can_change(definition, request, db)

        if request.name is not None and request.name != definition.name:
            existing_definition = self.repository.get_by_name(request.name, db)
            if existing_definition:
                raise ProcessConflictError(f"节点定义名称 {request.name} 已存在")
            definition.name = request.name

        if "description" in request.model_fields_set:
            definition.description = request.description
        if "icon" in request.model_fields_set:
            definition.icon = request.icon
        if request.config_schema_json is not None:
            definition.config_schema_json = deepcopy(request.config_schema_json)
        if request.ui_schema_json is not None:
            definition.ui_schema_json = deepcopy(request.ui_schema_json)
        if request.status is not None:
            definition.status = request.status

        definition.updated_at = utc_now()
        self.repository.add(definition, db)
        self._commit_or_conflict(db, "节点定义名称已存在")
        db.refresh(definition)
        return definition

    def _ensure_runtime_contract_can_change(
        self,
        definition: NodeDefinition,
        request: NodeDefinitionUpdateRequest,
        db: Session,
    ) -> None:
        """阻止修改已启用流程正在依赖的节点运行契约。

        配置 Schema 和启停状态会直接影响流程能否执行。已启用流程仍然引用当前
        节点定义时，只允许修改名称、说明、图标和界面 Schema 等展示信息。
        """

        schema_will_change = (
            request.config_schema_json is not None
            and request.config_schema_json != definition.config_schema_json
        )
        definition_will_be_disabled = (
            request.status == "DISABLED" and definition.status != "DISABLED"
        )
        if not schema_will_change and not definition_will_be_disabled:
            return

        if not self.process_repository.has_enabled_process_reference(definition.id, db):
            return

        raise ProcessConflictError(
            "节点定义已被启用流程引用，不能修改配置 Schema 或停用；"
            "请先停用相关流程，或者新建节点定义"
        )

    @staticmethod
    def _commit_or_conflict(db: Session, message: str) -> None:
        """提交事务，并将数据库唯一约束错误转换为领域冲突。"""

        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ProcessConflictError(message) from exc
