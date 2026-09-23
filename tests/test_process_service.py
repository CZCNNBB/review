"""审批流显式版本 Service 集成测试，需要可用的 PostgreSQL 数据库。"""

import unittest
from uuid import UUID, uuid4

from sqlmodel import Session

from app.server.organization.src.schemas.organization_schema import PersonCreateRequest
from app.server.organization.src.service.organization_service import OrganizationService
from app.server.process.src.models.process_model import ApprovalProcessVersionNode
from app.server.process.src.schemas.process_schema import (
    ProcessCreateRequest,
    ProcessGraphNodeRequest,
    ProcessGraphSaveRequest,
)
from app.server.process.src.service.exceptions import (
    ProcessConflictError,
    ProcessStateError,
)
from app.server.process.src.service.process_service import ProcessService
from tests.process_test_helpers import (
    DatabaseTestCaseMixin,
    load_seed_node_definitions,
)


class ProcessServiceTestCase(DatabaseTestCaseMixin, unittest.TestCase):
    """验证流程版本、草稿保存、发布和复制的核心事务。"""

    def setUp(self) -> None:
        """准备数据库会话、节点定义和一名有效审批人。"""

        self.db: Session = self.open_session()
        self.service = ProcessService()
        self.seed = load_seed_node_definitions()
        person = OrganizationService().create_person(
            PersonCreateRequest(name=f"流程版本测试人员-{uuid4().hex[:8]}"),
            self.db,
        )
        self.person_id = self.track_person(person.id)

    def tearDown(self) -> None:
        """清理当前用例创建的数据。"""

        self.close_session()

    def create_process(self) -> tuple[UUID, UUID]:
        """创建流程和 V1 草稿并返回两个 ID。"""

        overview = self.service.create_process(
            ProcessCreateRequest(
                name=f"版本测试流程-{uuid4().hex[:8]}",
                form_schema={
                    "type": "object",
                    "properties": {"amount": {"type": "number"}},
                },
            ),
            self.db,
        )
        self.track_process(overview.process.id)
        self.assertIsNotNone(overview.draft_version)
        return overview.process.id, overview.draft_version.id

    def build_graph_request(
        self,
        revision: int,
        name: str = "付款审批",
    ) -> ProcessGraphSaveRequest:
        """构造包含开始、人工审批和结束节点的合法整图请求。"""

        start_id = uuid4()
        approval_id = uuid4()
        end_id = uuid4()
        return ProcessGraphSaveRequest(
            revision=revision,
            name=name,
            form_schema={
                "type": "object",
                "properties": {"amount": {"type": "number"}},
            },
            nodes=[
                ProcessGraphNodeRequest(
                    id=start_id,
                    node_definition_id=self.seed["START"].id,
                    name="开始",
                    config={},
                    position={"x": 100, "y": 100},
                ),
                ProcessGraphNodeRequest(
                    id=approval_id,
                    node_definition_id=self.seed["APPROVAL"].id,
                    name="财务审批",
                    config={
                        "approval_mode": "AND",
                        "approvers": [{"person_id": str(self.person_id)}],
                    },
                    position={"x": 300, "y": 100},
                ),
                ProcessGraphNodeRequest(
                    id=end_id,
                    node_definition_id=self.seed["END"].id,
                    name="结束",
                    config={},
                    position={"x": 500, "y": 100},
                ),
            ],
            orchestration={
                "connections": [
                    {
                        "source_node_id": str(start_id),
                        "target_node_id": str(approval_id),
                    },
                    {
                        "source_node_id": str(approval_id),
                        "target_node_id": str(end_id),
                    },
                ]
            },
        )

    def test_create_process_also_creates_v1_draft(self) -> None:
        """创建流程时同步建立 revision=0 的 V1 草稿。"""

        process_id, draft_id = self.create_process()
        overview = self.service.get_overview(process_id, self.db)

        self.assertEqual(overview.process.status, "DRAFT")
        self.assertIsNone(overview.current_version)
        self.assertEqual(overview.draft_version.id, draft_id)
        self.assertEqual(overview.draft_version.version_no, 1)
        self.assertEqual(overview.draft_version.revision, 0)

    def test_save_graph_increments_revision_and_freezes_node_type(self) -> None:
        """保存草稿后修订号递增，版本节点同步固化执行类型。"""

        _, draft_id = self.create_process()
        graph = self.service.save_graph(
            draft_id,
            self.build_graph_request(revision=0),
            self.db,
        )

        self.assertEqual(graph.version.revision, 1)
        self.assertEqual(len(graph.nodes), 3)
        self.assertEqual(
            {node.node_type for node in graph.nodes},
            {"START", "APPROVAL", "END"},
        )

    def test_stale_revision_is_rejected_without_overwriting(self) -> None:
        """旧修订号保存返回冲突，已经保存的草稿保持不变。"""

        _, draft_id = self.create_process()
        self.service.save_graph(
            draft_id,
            self.build_graph_request(revision=0, name="第一次保存"),
            self.db,
        )

        with self.assertRaises(ProcessConflictError):
            self.service.save_graph(
                draft_id,
                self.build_graph_request(revision=0, name="过期保存"),
                self.db,
            )

        reloaded = self.service.get_graph(draft_id, self.db)
        self.assertEqual(reloaded.version.name, "第一次保存")
        self.assertEqual(reloaded.version.revision, 1)

    def test_publish_makes_version_immutable(self) -> None:
        """发布后流程指向该版本，原版本不再允许保存。"""

        process_id, draft_id = self.create_process()
        saved = self.service.save_graph(
            draft_id,
            self.build_graph_request(revision=0),
            self.db,
        )
        overview = self.service.publish_version(draft_id, self.db)

        self.assertEqual(overview.process.status, "ENABLED")
        self.assertEqual(overview.process.current_version_id, draft_id)
        self.assertEqual(overview.current_version.status, "PUBLISHED")
        self.assertIsNone(overview.draft_version)

        with self.assertRaises(ProcessStateError):
            self.service.save_graph(
                draft_id,
                self.build_graph_request(revision=saved.version.revision),
                self.db,
            )
        self.assertEqual(
            self.service.get_overview(process_id, self.db).current_version.id,
            draft_id,
        )

    def test_next_draft_clones_nodes_and_keeps_published_version(self) -> None:
        """V2 草稿复制 V1 内容并使用新的节点 ID，V1 保持不变。"""

        _, v1_id = self.create_process()
        v1_graph = self.service.save_graph(
            v1_id,
            self.build_graph_request(revision=0),
            self.db,
        )
        self.service.publish_version(v1_id, self.db)
        v2 = self.service.create_draft(v1_graph.process.id, self.db)
        v2_graph = self.service.get_graph(v2.id, self.db)

        self.assertEqual(v2.version_no, 2)
        self.assertEqual(v2.status, "DRAFT")
        self.assertEqual(len(v2_graph.nodes), len(v1_graph.nodes))
        self.assertFalse(
            {node.id for node in v1_graph.nodes}
            & {node.id for node in v2_graph.nodes}
        )
        self.assertEqual(
            self.service.get_graph(v1_id, self.db).version.status,
            "PUBLISHED",
        )

    def test_copy_process_creates_independent_v1_draft(self) -> None:
        """复制流程会创建独立流程、V1 草稿和全新节点 ID。"""

        process_id, draft_id = self.create_process()
        source_graph = self.service.save_graph(
            draft_id,
            self.build_graph_request(revision=0),
            self.db,
        )
        copied = self.service.copy_process(process_id, self.db)
        self.track_process(copied.process.id)
        copied_graph = self.service.get_graph(copied.draft_version.id, self.db)

        self.assertNotEqual(copied.process.id, process_id)
        self.assertEqual(copied.draft_version.version_no, 1)
        self.assertEqual(copied.draft_version.status, "DRAFT")
        self.assertFalse(
            {node.id for node in source_graph.nodes}
            & {node.id for node in copied_graph.nodes}
        )

    def test_json_in_place_mutation_is_not_persisted(self) -> None:
        """版本节点 JSON 仍要求整体赋值，防止 ORM 静默漏写。"""

        _, draft_id = self.create_process()
        graph = self.service.save_graph(
            draft_id,
            self.build_graph_request(revision=0),
            self.db,
        )
        approval_node = next(
            node for node in graph.nodes if node.node_type == "APPROVAL"
        )
        node = self.db.get(ApprovalProcessVersionNode, approval_node.id)
        node.config_json["approval_mode"] = "OR"
        self.db.commit()
        self.db.expire_all()

        reloaded = self.db.get(ApprovalProcessVersionNode, approval_node.id)
        self.assertEqual(reloaded.config_json["approval_mode"], "AND")


if __name__ == "__main__":
    unittest.main()
