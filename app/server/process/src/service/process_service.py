"""审批流主体、显式版本、版本节点和发布业务逻辑。"""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session

from app.server.organization.src.service.organization_service import OrganizationService
from app.server.process.src.constants import (
    NODE_ID_OCCUPIED_MESSAGE,
    NODE_TYPE_APPROVAL,
    PROCESS_COPY_NAME_BASE_MAX_LENGTH,
    PROCESS_COPY_NAME_SUFFIX,
    PROCESS_STATUS_DISABLED,
    PROCESS_STATUS_DRAFT,
    PROCESS_STATUS_ENABLED,
    PROCESS_VERSION_STATUS_DRAFT,
    PROCESS_VERSION_STATUS_PUBLISHED,
)
from app.server.process.src.models.process_model import (
    ApprovalProcess,
    ApprovalProcessVersion,
    ApprovalProcessVersionNode,
    NodeDefinition,
)
from app.server.process.src.repository.node_definition_repository import (
    NodeDefinitionRepository,
)
from app.server.process.src.repository.process_repository import ProcessRepository
from app.server.process.src.schemas.process_schema import (
    ProcessCreateRequest,
    ProcessGraphSaveRequest,
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
class ProcessOverview:
    """审批流列表和详情所需的版本摘要。"""

    process: ApprovalProcess
    current_version: ApprovalProcessVersion | None
    draft_version: ApprovalProcessVersion | None
    node_count: int


@dataclass(frozen=True)
class ProcessGraphView:
    """一个确定流程版本的完整画布数据。"""

    process: ApprovalProcess
    version: ApprovalProcessVersion
    nodes: tuple[ApprovalProcessVersionNode, ...]
    definitions: Mapping[UUID, NodeDefinition]


class ProcessService:
    """提供审批流、草稿版本、整图保存、复制、发布和停用能力。"""

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
    # 流程主体与版本
    # ------------------------------------------------------------------

    def create_process(
        self,
        request: ProcessCreateRequest,
        db: Session,
    ) -> ProcessOverview:
        """创建审批流主体和 V1 草稿。"""

        process = ApprovalProcess(
            name=request.name,
            description=request.description,
            status=PROCESS_STATUS_DRAFT,
        )
        draft_version = ApprovalProcessVersion(
            process_id=process.id,
            version_no=1,
            status=PROCESS_VERSION_STATUS_DRAFT,
            name=request.name,
            description=request.description,
            form_schema_json=deepcopy(request.form_schema),
            form_ui_schema_json=deepcopy(request.form_ui_schema),
            orchestration_json={"connections": []},
            revision=0,
        )
        self.repository.add_process(process, db)
        self.repository.add_version(draft_version, db)
        self._commit_or_conflict(db, "创建审批流失败，请重试")
        db.refresh(process)
        db.refresh(draft_version)
        return ProcessOverview(process, None, draft_version, 0)

    def get_process(self, process_id: UUID, db: Session) -> ApprovalProcess:
        """查询审批流，不存在时抛出领域异常。"""

        process = self.repository.get_process_by_id(process_id, db)
        if process is None:
            raise ProcessNotFoundError("审批流不存在")
        return process

    def get_version(self, version_id: UUID, db: Session) -> ApprovalProcessVersion:
        """查询流程版本，不存在时抛出领域异常。"""

        version = self.repository.get_version_by_id(version_id, db)
        if version is None:
            raise ProcessNotFoundError("审批流版本不存在")
        return version

    def get_overview(self, process_id: UUID, db: Session) -> ProcessOverview:
        """查询流程及当前版本、草稿版本和画布节点数量。"""

        process = self.get_process(process_id, db)
        return self._build_overview(process, db)

    def list_processes(
        self,
        db: Session,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ProcessOverview]:
        """分页查询审批流及版本摘要。"""

        processes = self.repository.list_processes(db, offset=offset, limit=limit)
        return [self._build_overview(process, db) for process in processes]

    def list_versions(
        self,
        process_id: UUID,
        db: Session,
    ) -> list[tuple[ApprovalProcessVersion, int]]:
        """查询流程全部版本并附带节点数量。"""

        self.get_process(process_id, db)
        versions = self.repository.list_versions(process_id, db)
        node_counts = self.repository.count_nodes_by_version_ids(
            [version.id for version in versions],
            db,
        )
        return [
            (version, node_counts.get(version.id, 0))
            for version in versions
        ]

    def create_draft(
        self,
        process_id: UUID,
        db: Session,
    ) -> ApprovalProcessVersion:
        """从当前发布版本复制下一版草稿；已有草稿时直接返回。"""

        existing_draft = self.repository.get_draft_version(process_id, db)
        if existing_draft is not None:
            return existing_draft

        process = self.repository.get_process_for_update(process_id, db)
        if process is None:
            raise ProcessNotFoundError("审批流不存在")
        # 获得流程行锁后必须再次查询，处理两个并发请求同时看到“没有草稿”的情况。
        existing_draft = self.repository.get_draft_version(process_id, db)
        if existing_draft is not None:
            return existing_draft
        if process.current_version_id is None:
            raise ProcessStateError("流程没有可复制的已发布版本")

        source_version = self.get_version(process.current_version_id, db)
        source_nodes = self.repository.list_nodes(source_version.id, db)
        draft_version = self._copy_version(
            process_id=process.id,
            source_version=source_version,
            source_nodes=source_nodes,
            version_no=self.repository.get_latest_version_no(process.id, db) + 1,
            name=source_version.name,
            db=db,
        )
        process.updated_at = utc_now()
        self.repository.add_process(process, db)
        self._commit_or_conflict(db, "创建草稿版本失败，可能已经存在其他草稿")
        db.refresh(draft_version)
        return draft_version

    def copy_process(self, process_id: UUID, db: Session) -> ProcessOverview:
        """把流程当前可见版本复制为一条新流程的 V1 草稿。"""

        source_process = self.get_process(process_id, db)
        source_version = self.repository.get_draft_version(process_id, db)
        if source_version is None and source_process.current_version_id is not None:
            source_version = self.get_version(source_process.current_version_id, db)
        if source_version is None:
            raise ProcessStateError("审批流没有可复制的版本")

        source_nodes = self.repository.list_nodes(source_version.id, db)
        copied_process = ApprovalProcess(
            name=self._build_copy_name(source_version.name),
            description=source_version.description,
            status=PROCESS_STATUS_DRAFT,
        )
        self.repository.add_process(copied_process, db)
        copied_version = self._copy_version(
            process_id=copied_process.id,
            source_version=source_version,
            source_nodes=source_nodes,
            version_no=1,
            name=copied_process.name,
            db=db,
        )
        self._commit_or_conflict(db, "复制审批流失败，请重试")
        db.refresh(copied_process)
        db.refresh(copied_version)
        return ProcessOverview(
            copied_process,
            None,
            copied_version,
            len(source_nodes),
        )

    def publish_version(
        self,
        version_id: UUID,
        db: Session,
    ) -> ProcessOverview:
        """校验并发布草稿版本，同时原子切换流程当前版本。"""

        version = self.repository.get_version_for_update(version_id, db)
        if version is None:
            raise ProcessNotFoundError("审批流版本不存在")
        process = self.repository.get_process_for_update(version.process_id, db)
        if process is None:
            raise ProcessNotFoundError("审批流不存在")
        if version.status == PROCESS_VERSION_STATUS_PUBLISHED:
            if process.current_version_id == version.id:
                return self._build_overview(process, db)
            raise ProcessStateError("历史发布版本不能再次设为当前版本")
        if version.status != PROCESS_VERSION_STATUS_DRAFT:
            raise ProcessStateError("只有草稿版本可以发布")

        issues = self.validate_version(version.id, db)
        if issues:
            raise ProcessValidationError("流程校验未通过，无法发布", issues)

        now = utc_now()
        version.status = PROCESS_VERSION_STATUS_PUBLISHED
        version.published_at = now
        version.updated_at = now
        process.current_version_id = version.id
        process.name = version.name
        process.description = version.description
        process.status = PROCESS_STATUS_ENABLED
        process.updated_at = now
        self.repository.add_version(version, db)
        self.repository.add_process(process, db)
        self._commit_or_conflict(db, "发布流程版本失败，请重试")
        db.refresh(process)
        db.refresh(version)
        return self._build_overview(process, db)

    def disable_process(self, process_id: UUID, db: Session) -> ProcessOverview:
        """停用已有发布版本的流程，不影响历史版本。"""

        process = self.repository.get_process_for_update(process_id, db)
        if process is None:
            raise ProcessNotFoundError("审批流不存在")
        if process.current_version_id is None:
            raise ProcessStateError("流程尚未发布，不需要停用")
        if process.status == PROCESS_STATUS_DISABLED:
            return self._build_overview(process, db)

        process.status = PROCESS_STATUS_DISABLED
        process.updated_at = utc_now()
        self.repository.add_process(process, db)
        self._commit_or_conflict(db, "停用审批流失败，请重试")
        db.refresh(process)
        return self._build_overview(process, db)

    # ------------------------------------------------------------------
    # 版本画布
    # ------------------------------------------------------------------

    def get_graph(self, version_id: UUID, db: Session) -> ProcessGraphView:
        """读取确定版本的主体、节点和节点定义。"""

        version = self.get_version(version_id, db)
        process = self.get_process(version.process_id, db)
        nodes = self.repository.list_nodes(version.id, db)
        definitions = self._load_definitions(
            (node.node_definition_id for node in nodes),
            db,
        )
        return ProcessGraphView(process, version, tuple(nodes), definitions)

    def save_graph(
        self,
        version_id: UUID,
        request: ProcessGraphSaveRequest,
        db: Session,
    ) -> ProcessGraphView:
        """使用 revision 乐观锁，在单个事务中保存草稿整图。"""

        version = self.repository.get_version_for_update(version_id, db)
        if version is None:
            raise ProcessNotFoundError("审批流版本不存在")
        if version.status != PROCESS_VERSION_STATUS_DRAFT:
            raise ProcessStateError("已发布版本不可修改，请先创建新草稿")
        if request.revision != version.revision:
            raise ProcessConflictError(
                f"草稿已被其他操作更新，当前修订号为 {version.revision}，请刷新后重试"
            )

        form_schema = self._resolve_form_schema(request, version)
        form_ui_schema = self._resolve_form_ui_schema(request, version)
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
        self._write_nodes(version.id, request.nodes, definitions, db)

        version.name = request.name
        if "description" in request.model_fields_set:
            version.description = request.description
        version.form_schema_json = deepcopy(form_schema)
        version.form_ui_schema_json = deepcopy(form_ui_schema)
        version.orchestration_json = serialize_connections(graph.connections)
        version.revision += 1
        version.updated_at = utc_now()
        self.repository.add_version(version, db)

        # 先 flush 再根据真正落库的对象复核，任何问题都回滚整次整图保存。
        db.flush()
        persisted_issues = self._validate_persisted(
            version,
            definitions,
            person_statuses,
            db,
        )
        if persisted_issues:
            db.rollback()
            raise ProcessValidationError(
                "流程校验未通过，请修正后重新保存",
                persisted_issues,
            )

        self._commit_or_conflict(db, "流程版本或节点数据冲突，请刷新后重试")
        db.refresh(version)
        return self.get_graph(version.id, db)

    def validate_version(
        self,
        version_id: UUID,
        db: Session,
    ) -> list[ValidationIssue]:
        """校验确定版本的完整性并返回全部问题。"""

        version = self.get_version(version_id, db)
        nodes = self.repository.list_nodes(version.id, db)
        node_inputs = [
            (node.id, node.node_definition_id, node.name, node.config_json)
            for node in nodes
        ]
        _, issues = self._build_and_validate(
            node_inputs,
            version.form_schema_json,
            version.orchestration_json,
            db,
        )
        return issues

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _build_overview(
        self,
        process: ApprovalProcess,
        db: Session,
    ) -> ProcessOverview:
        """组装审批流摘要，草稿存在时节点数量优先展示草稿。"""

        draft_version = self.repository.get_draft_version(process.id, db)
        current_version = None
        if process.current_version_id is not None:
            current_version = self.repository.get_version_by_id(
                process.current_version_id,
                db,
            )
        display_version = draft_version or current_version
        node_count = 0
        if display_version is not None:
            counts = self.repository.count_nodes_by_version_ids(
                [display_version.id],
                db,
            )
            node_count = counts.get(display_version.id, 0)
        return ProcessOverview(
            process=process,
            current_version=current_version,
            draft_version=draft_version,
            node_count=node_count,
        )

    def _copy_version(
        self,
        process_id: UUID,
        source_version: ApprovalProcessVersion,
        source_nodes: Sequence[ApprovalProcessVersionNode],
        version_no: int,
        name: str,
        db: Session,
    ) -> ApprovalProcessVersion:
        """复制版本和全部节点，并重写编排中的节点 ID。"""

        node_id_map = {node.id: uuid4() for node in source_nodes}
        copied_version = ApprovalProcessVersion(
            process_id=process_id,
            version_no=version_no,
            status=PROCESS_VERSION_STATUS_DRAFT,
            name=name,
            description=source_version.description,
            form_schema_json=deepcopy(source_version.form_schema_json),
            form_ui_schema_json=deepcopy(source_version.form_ui_schema_json),
            orchestration_json=remap_orchestration(
                source_version.orchestration_json or {"connections": []},
                node_id_map,
            ),
            revision=0,
        )
        self.repository.add_version(copied_version, db)
        for source_node in source_nodes:
            self.repository.add_node(
                ApprovalProcessVersionNode(
                    id=node_id_map[source_node.id],
                    process_version_id=copied_version.id,
                    node_definition_id=source_node.node_definition_id,
                    node_type=source_node.node_type,
                    name=source_node.name,
                    config_json=deepcopy(source_node.config_json),
                    position_json=deepcopy(source_node.position_json),
                ),
                db,
            )
        return copied_version

    def _write_nodes(
        self,
        version_id: UUID,
        requested_nodes: Sequence[Any],
        definitions: Mapping[UUID, NodeDefinition],
        db: Session,
    ) -> None:
        """按请求内容增删改草稿版本节点。"""

        existing_nodes = self.repository.list_nodes(version_id, db)
        existing_by_id = {node.id: node for node in existing_nodes}
        desired_ids = {node.id for node in requested_nodes}

        for removed_node_id in existing_by_id.keys() - desired_ids:
            self.repository.delete_node(existing_by_id[removed_node_id], db)
        db.flush()

        occupied_nodes = self.repository.list_nodes_by_ids(
            list(desired_ids - existing_by_id.keys()),
            db,
        )
        if occupied_nodes:
            db.rollback()
            raise ProcessConflictError(NODE_ID_OCCUPIED_MESSAGE)

        for requested_node in requested_nodes:
            definition = definitions[requested_node.node_definition_id]
            current_node = existing_by_id.get(requested_node.id)
            if current_node is None:
                self.repository.add_node(
                    ApprovalProcessVersionNode(
                        id=requested_node.id,
                        process_version_id=version_id,
                        node_definition_id=requested_node.node_definition_id,
                        node_type=definition.node_type,
                        name=requested_node.name,
                        config_json=deepcopy(requested_node.config),
                        position_json=deepcopy(requested_node.position),
                    ),
                    db,
                )
                continue

            current_node.node_definition_id = requested_node.node_definition_id
            current_node.node_type = definition.node_type
            current_node.name = requested_node.name
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
        """组装流程图并执行结构、节点和审批人校验。"""

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
        version: ApprovalProcessVersion,
        definitions: Mapping[UUID, NodeDefinition],
        person_statuses: Mapping[UUID, str],
        db: Session,
    ) -> list[ValidationIssue]:
        """按已经写入会话的版本节点和编排复核流程。"""

        persisted_nodes = self.repository.list_nodes(version.id, db)
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
            version.form_schema_json,
            version.orchestration_json,
        )
        persisted_issues.extend(
            validate_graph(
                persisted_graph,
                definitions=definitions,
                person_statuses=person_statuses,
            )
        )
        return persisted_issues

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
        """批量取回审批人状态，供审批节点校验。"""

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
        version: ApprovalProcessVersion,
    ) -> Any:
        """缺省表单规则时保留草稿现值。"""

        if "form_schema" in request.model_fields_set and request.form_schema is not None:
            return request.form_schema
        return version.form_schema_json

    @staticmethod
    def _resolve_form_ui_schema(
        request: ProcessGraphSaveRequest,
        version: ApprovalProcessVersion,
    ) -> Any:
        """缺省表单展示规则时保留草稿现值。"""

        if (
            "form_ui_schema" in request.model_fields_set
            and request.form_ui_schema is not None
        ):
            return request.form_ui_schema
        return version.form_ui_schema_json

    @staticmethod
    def _build_copy_name(source_name: str) -> str:
        """构造副本名称并保证不超过数据库字段长度。"""

        base_name = source_name[:PROCESS_COPY_NAME_BASE_MAX_LENGTH]
        return f"{base_name}{PROCESS_COPY_NAME_SUFFIX}"

    @staticmethod
    def _commit_or_conflict(db: Session, message: str) -> None:
        """提交事务，把唯一约束错误转换为领域冲突并保证回滚。"""

        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ProcessConflictError(message) from exc
        except SQLAlchemyError:
            db.rollback()
            raise
