"""审批流定义、流程编排保存与启停业务逻辑。"""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session

from app.server.organization.src.service.organization_service import (
    OrganizationService,
)
from app.server.process.src.constants import (
    NODE_ID_OCCUPIED_MESSAGE,
    NODE_TYPE_APPROVAL,
    PROCESS_COPY_NAME_BASE_MAX_LENGTH,
    PROCESS_COPY_NAME_SUFFIX,
    PROCESS_STATUS_DISABLED,
    PROCESS_STATUS_DRAFT,
    PROCESS_STATUS_ENABLED,
)
from app.server.process.src.models.process_model import (
    ApprovalProcess,
    ApprovalProcessNode,
    NodeDefinition,
)
from app.server.process.src.repository.node_definition_repository import (
    NodeDefinitionRepository,
)
from app.server.process.src.repository.process_repository import ProcessRepository
from app.server.process.src.schemas.process_schema import (
    ProcessCreateRequest,
    ProcessGraphSaveRequest,
    ProcessUpdateRequest,
)
from app.server.process.src.service.exceptions import (
    ProcessConflictError,
    ProcessNotFoundError,
    ProcessStateError,
    ProcessValidationError,
)
from app.server.process.src.service.process_validation import (
    ProcessGraph,
    ValidationIssue,
    build_graph,
    remap_orchestration,
    serialize_connections,
    validate_graph,
)


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""

    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ProcessGraphView:
    """整图读取结果，包含流程主体、节点实例和引用到的节点定义。"""

    process: ApprovalProcess
    nodes: tuple[ApprovalProcessNode, ...]
    definitions: Mapping[UUID, NodeDefinition]


class ProcessService:
    """提供审批流定义维护、整图保存、复制和启停能力。

    本模块只负责流程定义态。审批实例、运行快照、待办任务和业务回调都属于后续的
    审批运行模块与回调执行模块。
    """

    def __init__(
        self,
        repository: ProcessRepository | None = None,
        node_definition_repository: NodeDefinitionRepository | None = None,
        organization_service: OrganizationService | None = None,
    ):
        """初始化审批流服务并允许测试注入依赖。"""

        self.repository = repository or ProcessRepository()
        self.node_definition_repository = (
            node_definition_repository or NodeDefinitionRepository()
        )
        self.organization_service = organization_service or OrganizationService()

    # ------------------------------------------------------------------
    # 流程基本资料
    # ------------------------------------------------------------------

    def create_process(
        self,
        request: ProcessCreateRequest,
        db: Session,
    ) -> ApprovalProcess:
        """创建审批流，新建流程恒为草稿状态。"""

        process = ApprovalProcess(
            name=request.name,
            description=request.description,
            status=PROCESS_STATUS_DRAFT,
            form_schema_json=deepcopy(request.form_schema),
            form_ui_schema_json=deepcopy(request.form_ui_schema),
        )
        self.repository.add_process(process, db)
        self._commit_or_conflict(db, "创建审批流失败，请重试")
        db.refresh(process)
        return process

    def list_processes(
        self,
        db: Session,
        offset: int = 0,
        limit: int = 100,
    ) -> list[tuple[ApprovalProcess, int]]:
        """分页查询审批流并附带节点数量。"""

        processes = self.repository.list_processes(db, offset=offset, limit=limit)
        node_counts = self.repository.count_nodes_by_process_ids(
            [process.id for process in processes],
            db,
        )
        return [(process, node_counts.get(process.id, 0)) for process in processes]

    def get_process(self, process_id: UUID, db: Session) -> ApprovalProcess:
        """查询审批流，不存在时抛出领域异常。"""

        process = self.repository.get_process_by_id(process_id, db)
        if not process:
            raise ProcessNotFoundError("审批流不存在")
        return process

    def count_nodes(self, process_id: UUID, db: Session) -> int:
        """统计流程当前的节点数量。"""

        return len(self.repository.list_nodes(process_id, db))

    def update_process(
        self,
        process_id: UUID,
        request: ProcessUpdateRequest,
        db: Session,
    ) -> ApprovalProcess:
        """更新审批流基本资料和审批表单。

        修改审批表单可能让已有的条件分支引用到不存在的字段，因此表单变更时会按
        现有节点重新执行一次完整校验。
        """

        process = self.get_process(process_id, db)

        if "form_schema" in request.model_fields_set and request.form_schema is not None:
            self._ensure_form_schema_matches_graph(process, request.form_schema, db)
            process.form_schema_json = deepcopy(request.form_schema)
        if "form_ui_schema" in request.model_fields_set and request.form_ui_schema is not None:
            process.form_ui_schema_json = deepcopy(request.form_ui_schema)
        if request.name is not None:
            process.name = request.name
        if "description" in request.model_fields_set:
            process.description = request.description

        process.updated_at = utc_now()
        self.repository.add_process(process, db)
        self._commit_or_conflict(db, "更新审批流失败，请重试")
        db.refresh(process)
        return process

    def copy_process(self, process_id: UUID, db: Session) -> ApprovalProcess:
        """复制审批流，新流程包含全新节点 ID 且保持草稿状态。"""

        source_process = self.get_process(process_id, db)
        source_nodes = self.repository.list_nodes(process_id, db)

        node_id_map = {node.id: uuid4() for node in source_nodes}
        orchestration = remap_orchestration(
            source_process.orchestration_json or {"connections": []},
            node_id_map,
        )

        copied_process = ApprovalProcess(
            name=self._build_copy_name(source_process.name),
            description=source_process.description,
            status=PROCESS_STATUS_DRAFT,
            form_schema_json=deepcopy(source_process.form_schema_json),
            form_ui_schema_json=deepcopy(source_process.form_ui_schema_json),
            orchestration_json=orchestration,
        )
        self.repository.add_process(copied_process, db)

        for source_node in source_nodes:
            # 必须深拷贝：否则源流程与副本会在同一个会话里共享同一批字典对象。
            self.repository.add_node(
                ApprovalProcessNode(
                    id=node_id_map[source_node.id],
                    process_id=copied_process.id,
                    node_definition_id=source_node.node_definition_id,
                    name=source_node.name,
                    config_json=deepcopy(source_node.config_json),
                    position_json=deepcopy(source_node.position_json),
                ),
                db,
            )

        self._commit_or_conflict(db, "复制审批流失败，请重试")
        db.refresh(copied_process)
        return copied_process

    # ------------------------------------------------------------------
    # 流程状态迁移
    # ------------------------------------------------------------------

    def enable_process(self, process_id: UUID, db: Session) -> ApprovalProcess:
        """启用审批流，只有完整性校验通过才允许启用。"""

        process = self.get_process(process_id, db)
        if process.status == PROCESS_STATUS_ENABLED:
            return process

        issues = self.validate_process(process_id, db)
        if issues:
            raise ProcessValidationError("流程校验未通过，无法启用", issues)

        process.status = PROCESS_STATUS_ENABLED
        process.updated_at = utc_now()
        self.repository.add_process(process, db)
        self._commit_or_conflict(db, "启用审批流失败，请重试")
        db.refresh(process)
        return process

    def disable_process(self, process_id: UUID, db: Session) -> ApprovalProcess:
        """停用审批流，已经停用时直接返回当前状态。"""

        process = self.get_process(process_id, db)
        if process.status == PROCESS_STATUS_DRAFT:
            raise ProcessStateError("草稿流程不需要停用，请先完成并启用流程")
        if process.status == PROCESS_STATUS_DISABLED:
            return process

        process.status = PROCESS_STATUS_DISABLED
        process.updated_at = utc_now()
        self.repository.add_process(process, db)
        self._commit_or_conflict(db, "停用审批流失败，请重试")
        db.refresh(process)
        return process

    # ------------------------------------------------------------------
    # 流程编排
    # ------------------------------------------------------------------

    def get_graph(self, process_id: UUID, db: Session) -> ProcessGraphView:
        """读取流程主体、全部节点实例和引用到的节点定义。"""

        process = self.get_process(process_id, db)
        nodes = self.repository.list_nodes(process_id, db)
        definitions = self._load_definitions(
            (node.node_definition_id for node in nodes),
            db,
        )
        return ProcessGraphView(
            process=process,
            nodes=tuple(nodes),
            definitions=definitions,
        )

    def save_graph(
        self,
        process_id: UUID,
        request: ProcessGraphSaveRequest,
        db: Session,
    ) -> ProcessGraphView:
        """在单个事务中保存完整流程、节点和编排。

        先做写前全量校验，任何一步失败都不写入数据；写入完成后再按落库状态复核
        一次，复核不通过则整体回滚。
        """

        process = self.get_process(process_id, db)

        form_schema = self._resolve_form_schema(request, process)
        form_ui_schema = self._resolve_form_ui_schema(request, process)

        node_inputs = [
            (node.id, node.node_definition_id, node.name, node.config)
            for node in request.nodes
        ]
        graph, issues = self._build_and_validate(
            node_inputs,
            form_schema,
            request.orchestration,
            db,
        )
        if issues:
            raise ProcessValidationError("流程校验未通过，请修正后重新保存", issues)

        definitions = self._load_definitions(
            (node.node_definition_id for node in graph.nodes),
            db,
        )
        person_statuses = self._load_person_statuses(graph, definitions, db)

        self._write_nodes(process_id, request.nodes, db)

        process.name = request.name
        # 说明缺省时保留原值，显式传 null 才会清空，与表单字段保持一致语义。
        if "description" in request.model_fields_set:
            process.description = request.description
        process.form_schema_json = deepcopy(form_schema)
        process.form_ui_schema_json = deepcopy(form_ui_schema)
        process.orchestration_json = serialize_connections(graph.connections)
        process.updated_at = utc_now()
        self.repository.add_process(process, db)

        # 让后续读回能看到本次未提交的写入，再按落库状态复核一次。
        db.flush()
        persisted_issues = self._validate_persisted(
            process,
            definitions,
            person_statuses,
            db,
        )
        if persisted_issues:
            db.rollback()
            raise ProcessValidationError("流程校验未通过，请修正后重新保存", persisted_issues)

        self._commit_or_conflict(db, "流程节点数据冲突，请重试")
        db.refresh(process)
        return self.get_graph(process_id, db)

    def validate_process(
        self,
        process_id: UUID,
        db: Session,
    ) -> list[ValidationIssue]:
        """按当前定义校验流程完整性，返回全部问题。"""

        process = self.get_process(process_id, db)
        nodes = self.repository.list_nodes(process_id, db)
        node_inputs = [
            (node.id, node.node_definition_id, node.name, node.config_json)
            for node in nodes
        ]
        _, issues = self._build_and_validate(
            node_inputs,
            process.form_schema_json,
            process.orchestration_json,
            db,
        )
        return issues

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _write_nodes(
        self,
        process_id: UUID,
        requested_nodes: Sequence[Any],
        db: Session,
    ) -> None:
        """按请求内容增删改节点实例。"""

        existing_nodes = self.repository.list_nodes(process_id, db)
        existing_by_id = {node.id: node for node in existing_nodes}
        desired_ids = {node.id for node in requested_nodes}

        for removed_node_id in existing_by_id.keys() - desired_ids:
            self.repository.delete_node(existing_by_id[removed_node_id], db)
        # 先落库删除，避免同一批语句里出现删除与新增同一主键的顺序问题。
        db.flush()

        # 节点 ID 由前端生成，必须确认没有被其它流程占用，否则会覆盖别人的数据。
        occupied_nodes = self.repository.list_nodes_by_ids(
            list(desired_ids - existing_by_id.keys()),
            db,
        )
        if occupied_nodes:
            db.rollback()
            raise ProcessConflictError(NODE_ID_OCCUPIED_MESSAGE)

        for requested_node in requested_nodes:
            current_node = existing_by_id.get(requested_node.id)
            if current_node is None:
                self.repository.add_node(
                    ApprovalProcessNode(
                        id=requested_node.id,
                        process_id=process_id,
                        node_definition_id=requested_node.node_definition_id,
                        name=requested_node.name,
                        config_json=deepcopy(requested_node.config),
                        position_json=deepcopy(requested_node.position),
                    ),
                    db,
                )
                continue

            current_node.node_definition_id = requested_node.node_definition_id
            current_node.name = requested_node.name
            # JSON 字段必须整体重新赋值，原地修改不会被 SQLAlchemy 侦测。
            current_node.config_json = deepcopy(requested_node.config)
            current_node.position_json = deepcopy(requested_node.position)
            current_node.updated_at = utc_now()
            self.repository.add_node(current_node, db)

    def _build_and_validate(
        self,
        node_inputs: Iterable[tuple[UUID, UUID, str, Any]],
        form_schema: Any,
        orchestration: Any,
        db: Session,
    ) -> tuple[ProcessGraph, list[ValidationIssue]]:
        """组装流程视图并执行完整校验。"""

        graph, issues = build_graph(node_inputs, form_schema, orchestration)
        definitions = self._load_definitions(
            (node.node_definition_id for node in graph.nodes),
            db,
        )
        person_statuses = self._load_person_statuses(graph, definitions, db)
        issues.extend(
            validate_graph(
                graph,
                definitions=definitions,
                person_statuses=person_statuses,
            )
        )
        return graph, issues

    def _validate_persisted(
        self,
        process: ApprovalProcess,
        definitions: Mapping[UUID, NodeDefinition],
        person_statuses: Mapping[UUID, str],
        db: Session,
    ) -> list[ValidationIssue]:
        """按已经落库的节点和编排复核一次流程完整性。"""

        persisted_nodes = self.repository.list_nodes(process.id, db)
        persisted_graph, persisted_issues = build_graph(
            (
                (
                    node.id,
                    node.node_definition_id,
                    node.name,
                    node.config_json,
                )
                for node in persisted_nodes
            ),
            process.form_schema_json,
            process.orchestration_json,
        )
        persisted_issues.extend(
            validate_graph(
                persisted_graph,
                definitions=definitions,
                person_statuses=person_statuses,
            )
        )
        return persisted_issues

    def _ensure_form_schema_matches_graph(
        self,
        process: ApprovalProcess,
        form_schema: Mapping[str, Any],
        db: Session,
    ) -> None:
        """确认新表单仍然满足现有条件分支的字段引用。"""

        nodes = self.repository.list_nodes(process.id, db)
        node_inputs = [
            (node.id, node.node_definition_id, node.name, node.config_json)
            for node in nodes
        ]
        _, issues = self._build_and_validate(
            node_inputs,
            form_schema,
            process.orchestration_json,
            db,
        )
        if issues:
            raise ProcessValidationError("审批表单校验未通过，请修正后重试", issues)

    def _load_definitions(
        self,
        node_definition_ids: Iterable[UUID],
        db: Session,
    ) -> dict[UUID, NodeDefinition]:
        """批量取回节点定义并建立 ID 索引。"""

        unique_definition_ids = list(dict.fromkeys(node_definition_ids))
        definitions = self.node_definition_repository.list_by_ids(
            unique_definition_ids,
            db,
        )
        return {definition.id: definition for definition in definitions}

    def _load_person_statuses(
        self,
        graph: ProcessGraph,
        definitions: Mapping[UUID, NodeDefinition],
        db: Session,
    ) -> dict[UUID, str]:
        """批量取回审批人状态，供审批节点校验引用。"""

        person_ids: list[UUID] = []
        for node in graph.nodes:
            definition = definitions.get(node.node_definition_id)
            if definition is None or definition.node_type != NODE_TYPE_APPROVAL:
                continue

            raw_approvers = node.config.get("approvers")
            if not isinstance(raw_approvers, Sequence) or isinstance(raw_approvers, str):
                continue
            for raw_approver in raw_approvers:
                if not isinstance(raw_approver, Mapping):
                    continue
                raw_person_id = raw_approver.get("person_id")
                try:
                    person_ids.append(UUID(str(raw_person_id)))
                except (TypeError, ValueError):
                    continue

        unique_person_ids = list(dict.fromkeys(person_ids))
        if not unique_person_ids:
            return {}

        persons = self.organization_service.list_persons_by_ids(unique_person_ids, db)
        return {person.id: person.status for person in persons}

    @staticmethod
    def _resolve_form_schema(
        request: ProcessGraphSaveRequest,
        process: ApprovalProcess,
    ) -> Any:
        """缺省表单字段时保留流程原有表单，避免前端漏传把表单清空。"""

        if "form_schema" in request.model_fields_set and request.form_schema is not None:
            return request.form_schema
        return process.form_schema_json

    @staticmethod
    def _resolve_form_ui_schema(
        request: ProcessGraphSaveRequest,
        process: ApprovalProcess,
    ) -> Any:
        """缺省表单展示字段时保留流程原有展示规则。"""

        if (
            "form_ui_schema" in request.model_fields_set
            and request.form_ui_schema is not None
        ):
            return request.form_ui_schema
        return process.form_ui_schema_json

    @staticmethod
    def _build_copy_name(source_name: str) -> str:
        """构造副本名称，按字段长度截断避免超出数据库列长度。"""

        base_name = source_name[:PROCESS_COPY_NAME_BASE_MAX_LENGTH]
        return f"{base_name}{PROCESS_COPY_NAME_SUFFIX}"

    @staticmethod
    def _commit_or_conflict(db: Session, message: str) -> None:
        """提交事务，并把数据库错误转换为领域异常且保证回滚。"""

        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ProcessConflictError(message) from exc
        except SQLAlchemyError:
            # 其它数据库错误先回滚，避免把半截事务留在会话里。
            db.rollback()
            raise
