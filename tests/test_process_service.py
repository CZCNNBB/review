"""审批流服务层测试，覆盖整图保存事务、复制和状态迁移。

本文件需要可用的 PostgreSQL 数据库（表结构由 data/init.sql 初始化），不依赖
SQLite。测试只清理自己显式登记过的记录。
"""

import unittest
from uuid import UUID, uuid4

from sqlmodel import Session

from tests.process_test_helpers import (
    DatabaseTestCaseMixin,
    load_seed_node_definitions,
)
from app.server.organization.src.schemas.organization_schema import PersonCreateRequest
from app.server.organization.src.service.organization_service import OrganizationService
from app.server.process.src.constants import (
    NODE_ID_OCCUPIED_MESSAGE,
    RULE_NODE_UNREACHABLE,
)
from app.server.process.src.models.process_model import ApprovalProcessNode
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
from app.server.process.src.service.process_service import ProcessService


class ProcessServiceTestCase(DatabaseTestCaseMixin, unittest.TestCase):
    """验证审批流定义保存与维护的核心链路。"""

    def setUp(self) -> None:
        """准备会话、服务、seed 节点定义和一名测试人员。"""

        self.db: Session = self.open_session()
        self.service = ProcessService()
        self.organization_service = OrganizationService()
        self.seed = load_seed_node_definitions()

        person = self.organization_service.create_person(
            PersonCreateRequest(name=f"审批流测试人员-{uuid4().hex[:8]}"),
            self.db,
        )
        self.track_person(person.id)
        self.person_id = person.id

    def tearDown(self) -> None:
        """清理测试数据并关闭会话。"""

        self.close_session()

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def create_process(self, name: str | None = None):
        """创建一条测试流程并登记清理。"""

        process = self.service.create_process(
            ProcessCreateRequest(
                name=name or f"测试流程-{uuid4().hex[:8]}",
                form_schema={
                    "type": "object",
                    "properties": {"amount": {"type": "number"}},
                },
            ),
            self.db,
        )
        return self.track_process(process.id)

    def node_payload(
        self,
        node_id: UUID,
        node_type: str,
        name: str,
        config: dict | None = None,
    ) -> dict:
        """构造整图保存请求中的节点。"""

        if config is None:
            if node_type == "APPROVAL":
                config = {
                    "approval_mode": "AND",
                    "approvers": [{"person_id": str(self.person_id)}],
                }
            elif node_type == "END":
                config = {"result_status": "APPROVED"}
            else:
                config = {}
        return {
            "id": str(node_id),
            "node_definition_id": str(self.seed[node_type].id),
            "name": name,
            "config": config,
            "position": {"x": 100, "y": 200},
        }

    def graph_request(
        self,
        process,
        nodes: list[dict],
        connections: list[dict],
        *,
        name: str | None = None,
    ) -> ProcessGraphSaveRequest:
        """构造整图保存请求。"""

        return ProcessGraphSaveRequest(
            name=name or process.name,
            orchestration={"connections": connections},
            nodes=nodes,
        )

    def connection(self, source: UUID, target: UUID) -> dict:
        """构造一条无条件的编排连线。"""

        return {"source_node_id": str(source), "target_node_id": str(target)}

    def conditional_connection(
        self,
        source: UUID,
        target: UUID,
        *,
        field: str = "approval_form.amount",
        operator: str = "GT",
        value: int = 10000,
    ) -> dict:
        """构造一条带条件的编排连线。"""

        return {
            "source_node_id": str(source),
            "target_node_id": str(target),
            "condition": {"field": field, "operator": operator, "value": value},
        }

    def default_connection(self, source: UUID, target: UUID) -> dict:
        """构造一条默认路径连线。"""

        return {
            "source_node_id": str(source),
            "target_node_id": str(target),
            "default": True,
        }

    def save_valid_graph(self, process_id: UUID):
        """保存一条最小合法流程并返回三个节点 ID。"""

        process = self.service.get_process(process_id, self.db)
        start_id, approval_id, end_id = uuid4(), uuid4(), uuid4()
        self.service.save_graph(
            process_id,
            self.graph_request(
                process,
                [
                    self.node_payload(start_id, "START", "开始"),
                    self.node_payload(approval_id, "APPROVAL", "财务审批"),
                    self.node_payload(end_id, "END", "结束"),
                ],
                [
                    self.connection(start_id, approval_id),
                    self.connection(approval_id, end_id),
                ],
            ),
            self.db,
        )
        return start_id, approval_id, end_id

    # ------------------------------------------------------------------
    # 基本资料
    # ------------------------------------------------------------------

    def test_create_process_is_draft(self) -> None:
        """新建流程恒为草稿状态。"""

        process = self.service.get_process(self.create_process(), self.db)
        self.assertEqual(process.status, "DRAFT")

    def test_get_process_raises_when_missing(self) -> None:
        """查询不存在的流程时抛出领域异常。"""

        with self.assertRaises(ProcessNotFoundError):
            self.service.get_process(uuid4(), self.db)

    def test_list_processes_returns_node_count(self) -> None:
        """列表返回每条流程的节点数量。"""

        process_id = self.create_process()
        self.save_valid_graph(process_id)

        listed = {process.id: count for process, count in self.service.list_processes(self.db)}
        self.assertEqual(listed[process_id], 3)

    def test_update_process_keeps_nodes(self) -> None:
        """更新名称不影响已有节点。"""

        process_id = self.create_process()
        self.save_valid_graph(process_id)

        updated = self.service.update_process(
            process_id,
            ProcessUpdateRequest(name="改名后的流程"),
            self.db,
        )
        self.assertEqual(updated.name, "改名后的流程")
        self.assertEqual(self.service.count_nodes(process_id, self.db), 3)

    # ------------------------------------------------------------------
    # 整图保存
    # ------------------------------------------------------------------

    def test_save_graph_creates_updates_and_removes_nodes(self) -> None:
        """整图保存支持新增、更新和删除节点三种变化。"""

        process_id = self.create_process()
        start_id, approval_id, end_id = self.save_valid_graph(process_id)

        # 追加一个拒绝出口，同时改掉原审批节点的名称和审批模式。
        reject_end_id = uuid4()
        process = self.service.get_process(process_id, self.db)
        self.service.save_graph(
            process_id,
            self.graph_request(
                process,
                [
                    self.node_payload(start_id, "START", "开始"),
                    self.node_payload(approval_id, "APPROVAL", "财务审批改", {
                        "approval_mode": "OR",
                        "approvers": [{"person_id": str(self.person_id)}],
                    }),
                    self.node_payload(end_id, "END", "结束"),
                    self.node_payload(
                        reject_end_id,
                        "END",
                        "拒绝结束",
                        {"result_status": "REJECTED"},
                    ),
                ],
                [
                    self.connection(start_id, approval_id),
                    self.conditional_connection(approval_id, end_id),
                    self.default_connection(approval_id, reject_end_id),
                ],
            ),
            self.db,
        )

        nodes = {node.id: node for node in self.service.get_graph(process_id, self.db).nodes}
        self.assertEqual(set(nodes), {start_id, approval_id, end_id, reject_end_id})
        self.assertEqual(nodes[approval_id].name, "财务审批改")
        self.assertEqual(nodes[approval_id].config_json["approval_mode"], "OR")

        # 去掉追加的结束节点，确认节点被真正删除。
        process = self.service.get_process(process_id, self.db)
        self.service.save_graph(
            process_id,
            self.graph_request(
                process,
                [
                    self.node_payload(start_id, "START", "开始"),
                    self.node_payload(approval_id, "APPROVAL", "财务审批改"),
                    self.node_payload(end_id, "END", "结束"),
                ],
                [
                    self.connection(start_id, approval_id),
                    self.connection(approval_id, end_id),
                ],
            ),
            self.db,
        )
        remaining_ids = {node.id for node in self.service.get_graph(process_id, self.db).nodes}
        self.assertEqual(remaining_ids, {start_id, approval_id, end_id})

    def test_save_graph_rolls_back_on_validation_failure(self) -> None:
        """校验失败时不写入任何数据，已有节点和更新时间保持不变。"""

        process_id = self.create_process()
        start_id, approval_id, end_id = self.save_valid_graph(process_id)
        before_updated_at = self.service.get_process(process_id, self.db).updated_at

        process = self.service.get_process(process_id, self.db)
        with self.assertRaises(ProcessValidationError) as context:
            self.service.save_graph(
                process_id,
                self.graph_request(
                    process,
                    [
                        self.node_payload(start_id, "START", "开始"),
                        self.node_payload(approval_id, "APPROVAL", "财务审批"),
                        self.node_payload(end_id, "END", "结束"),
                        self.node_payload(uuid4(), "END", "孤立结束"),
                    ],
                    [
                        self.connection(start_id, approval_id),
                        self.connection(approval_id, end_id),
                    ],
                ),
                self.db,
            )

        self.assertIn(RULE_NODE_UNREACHABLE, [issue.code for issue in context.exception.issues])

        self.db.rollback()
        self.assertEqual(self.service.count_nodes(process_id, self.db), 3)
        self.assertEqual(
            self.service.get_process(process_id, self.db).updated_at,
            before_updated_at,
        )

    def test_save_graph_rejects_node_owned_by_other_process(self) -> None:
        """节点 ID 被别的流程占用时拒绝保存，且不影响对方数据。"""

        owner_process_id = self.create_process()
        owner_start_id, owner_approval_id, owner_end_id = self.save_valid_graph(
            owner_process_id
        )

        # 提交一张本身合法、但复用了对方审批节点 ID 的流程图。
        other_process_id = self.create_process()
        other_process = self.service.get_process(other_process_id, self.db)
        other_start_id, other_end_id = uuid4(), uuid4()

        with self.assertRaises(ProcessConflictError) as context:
            self.service.save_graph(
                other_process_id,
                self.graph_request(
                    other_process,
                    [
                        self.node_payload(other_start_id, "START", "开始"),
                        self.node_payload(owner_approval_id, "APPROVAL", "财务审批"),
                        self.node_payload(other_end_id, "END", "结束"),
                    ],
                    [
                        self.connection(other_start_id, owner_approval_id),
                        self.connection(owner_approval_id, other_end_id),
                    ],
                ),
                self.db,
            )
        self.assertEqual(str(context.exception), NODE_ID_OCCUPIED_MESSAGE)

        # 被占用的节点仍属于原流程，内容没有被改写。
        owner_nodes = {
            node.id: node for node in self.service.get_graph(owner_process_id, self.db).nodes
        }
        self.assertEqual(
            set(owner_nodes),
            {owner_start_id, owner_approval_id, owner_end_id},
        )
        self.assertEqual(owner_nodes[owner_approval_id].name, "财务审批")

        # 发起冲突的流程没有留下任何节点。
        self.assertEqual(self.service.count_nodes(other_process_id, self.db), 0)

    def test_save_graph_rejects_unknown_approver(self) -> None:
        """审批人不存在时保存失败。"""

        process_id = self.create_process()
        process = self.service.get_process(process_id, self.db)
        start_id, approval_id, end_id = uuid4(), uuid4(), uuid4()

        with self.assertRaises(ProcessValidationError):
            self.service.save_graph(
                process_id,
                self.graph_request(
                    process,
                    [
                        self.node_payload(start_id, "START", "开始"),
                        self.node_payload(
                            approval_id,
                            "APPROVAL",
                            "财务审批",
                            {
                                "approval_mode": "AND",
                                "approvers": [{"person_id": str(uuid4())}],
                            },
                        ),
                        self.node_payload(end_id, "END", "结束"),
                    ],
                    [
                        self.connection(start_id, approval_id),
                        self.connection(approval_id, end_id),
                    ],
                ),
                self.db,
            )

        self.db.rollback()
        self.assertEqual(self.service.count_nodes(process_id, self.db), 0)

    def test_save_graph_keeps_form_when_not_provided(self) -> None:
        """请求未提供表单时保留流程原有表单。"""

        process_id = self.create_process()
        self.save_valid_graph(process_id)

        process = self.service.get_process(process_id, self.db)
        original_form_schema = process.form_schema_json
        self.assertEqual(original_form_schema["properties"]["amount"]["type"], "number")

    # ------------------------------------------------------------------
    # 状态迁移
    # ------------------------------------------------------------------

    def test_enable_requires_valid_graph(self) -> None:
        """校验不通过的流程不能启用。"""

        process_id = self.create_process()
        with self.assertRaises(ProcessValidationError):
            self.service.enable_process(process_id, self.db)

        self.db.rollback()
        self.assertEqual(self.service.get_process(process_id, self.db).status, "DRAFT")

    def test_enable_and_disable_transitions(self) -> None:
        """草稿启用后可停用，重复启用和重复停用都是幂等的。"""

        process_id = self.create_process()
        self.save_valid_graph(process_id)

        enabled = self.service.enable_process(process_id, self.db)
        self.assertEqual(enabled.status, "ENABLED")
        self.assertEqual(self.service.enable_process(process_id, self.db).status, "ENABLED")

        disabled = self.service.disable_process(process_id, self.db)
        self.assertEqual(disabled.status, "DISABLED")
        self.assertEqual(self.service.disable_process(process_id, self.db).status, "DISABLED")

        # 停用后仍可重新启用。
        self.assertEqual(self.service.enable_process(process_id, self.db).status, "ENABLED")

    def test_disable_rejects_draft(self) -> None:
        """草稿流程不允许停用。"""

        process_id = self.create_process()
        with self.assertRaises(ProcessStateError):
            self.service.disable_process(process_id, self.db)

    # ------------------------------------------------------------------
    # 复制
    # ------------------------------------------------------------------

    def test_copy_process_remaps_nodes_and_isolates_json(self) -> None:
        """复制生成全新节点 ID，改写编排端点，且与源流程互不影响。"""

        process_id = self.create_process()
        start_id, approval_id, end_id = self.save_valid_graph(process_id)
        self.service.enable_process(process_id, self.db)

        copied = self.service.copy_process(process_id, self.db)
        self.track_process(copied.id)

        self.assertNotEqual(copied.id, process_id)
        self.assertEqual(copied.status, "DRAFT")
        self.assertTrue(copied.name.endswith("（副本）"))

        copied_graph = self.service.get_graph(copied.id, self.db)
        copied_node_ids = {node.id for node in copied_graph.nodes}
        self.assertEqual(len(copied_node_ids), 3)
        self.assertFalse(copied_node_ids & {start_id, approval_id, end_id})

        # 编排端点全部指向新节点。
        connection_node_ids = set()
        for connection in copied_graph.process.orchestration_json["connections"]:
            connection_node_ids.add(UUID(connection["source_node_id"]))
            connection_node_ids.add(UUID(connection["target_node_id"]))
        self.assertTrue(connection_node_ids.issubset(copied_node_ids))

        # 修改副本的节点配置不会影响源流程。
        copied_approval_id = next(
            node.id
            for node in copied_graph.nodes
            if node.node_definition_id == self.seed["APPROVAL"].id
        )
        copied_node = self.db.get(ApprovalProcessNode, copied_approval_id)
        copied_node.config_json = {
            "approval_mode": "OR",
            "approvers": [{"person_id": str(self.person_id)}],
        }
        self.db.commit()

        source_nodes = {
            node.id: node for node in self.service.get_graph(process_id, self.db).nodes
        }
        self.assertEqual(source_nodes[approval_id].config_json["approval_mode"], "AND")

    # ------------------------------------------------------------------
    # JSON 列写入约束
    # ------------------------------------------------------------------

    def test_in_place_json_mutation_is_not_persisted(self) -> None:
        """原地修改 JSON 字段不会被 SQLAlchemy 侦测，必须整体重新赋值。

        这条用例把「JSON 字段禁止原地修改」的约定钉死：如果将来有人依赖原地修改，
        这里会失败并提醒改成整体赋值。
        """

        process_id = self.create_process()
        _, approval_id, _ = self.save_valid_graph(process_id)

        node = self.db.get(ApprovalProcessNode, approval_id)
        node.config_json["approval_mode"] = "OR"
        self.db.commit()
        self.db.expire_all()

        reloaded = self.db.get(ApprovalProcessNode, approval_id)
        self.assertEqual(reloaded.config_json["approval_mode"], "AND")

        # 整体重新赋值才会被写入。
        reloaded.config_json = {
            "approval_mode": "OR",
            "approvers": [{"person_id": str(self.person_id)}],
        }
        self.db.commit()
        self.db.expire_all()
        self.assertEqual(
            self.db.get(ApprovalProcessNode, approval_id).config_json["approval_mode"],
            "OR",
        )


if __name__ == "__main__":
    unittest.main()
