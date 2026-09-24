"""审批流显式版本管理接口集成测试，需要可用的 PostgreSQL 数据库。"""

import os
import unittest
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.main import create_app
from app.server.organization.src.schemas.organization_schema import PersonCreateRequest
from app.server.organization.src.service.organization_service import OrganizationService
from tests.process_test_helpers import (
    DatabaseTestCaseMixin,
    load_builtin_node_definitions,
)


class ProcessApiTestCase(DatabaseTestCaseMixin, unittest.TestCase):
    """验证版本化审批流管理接口的完整链路。"""

    def setUp(self) -> None:
        """准备测试应用、管理密钥和测试审批人。"""

        self.previous_admin_key = os.environ.get("APPROVAL_ADMIN_KEY")
        os.environ["APPROVAL_ADMIN_KEY"] = "test-admin-key"
        self.admin_headers = {"X-Admin-Key": "test-admin-key"}
        self.db: Session = self.open_session()
        self.seed = load_builtin_node_definitions()

        person = OrganizationService().create_person(
            PersonCreateRequest(name=f"版本接口测试人员-{uuid4().hex[:8]}"),
            self.db,
        )
        self.person_id = self.track_person(person.id)
        app = create_app()

        def override_database_session():
            """为接口测试提供真实数据库会话。"""

            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_postgres_engine] = override_database_session
        self.client = TestClient(app)

    def tearDown(self) -> None:
        """关闭客户端、清理测试数据并恢复环境变量。"""

        self.client.close()
        self.close_session()
        if self.previous_admin_key is None:
            os.environ.pop("APPROVAL_ADMIN_KEY", None)
        else:
            os.environ["APPROVAL_ADMIN_KEY"] = self.previous_admin_key

    def create_process(self) -> tuple[str, str]:
        """通过接口创建流程，返回流程 ID 和 V1 草稿 ID。"""

        response = self.client.post(
            "/api/admin/processes",
            headers=self.admin_headers,
            json={
                "name": f"版本接口流程-{uuid4().hex[:8]}",
                "form_schema": {
                    "type": "object",
                    "properties": {"amount": {"type": "number"}},
                },
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        data = response.json()["data"]
        self.track_process(UUID(data["id"]))
        self.assertEqual(data["draft_version_no"], 1)
        return data["id"], data["draft_version_id"]

    def build_graph_payload(
        self,
        revision: int,
        name: str = "付款审批",
    ) -> dict:
        """构造一个最小合法版本整图。"""

        start_id = uuid4()
        approval_id = uuid4()
        end_id = uuid4()
        return {
            "revision": revision,
            "name": name,
            "nodes": [
                {
                    "id": str(start_id),
                    "node_definition_id": str(self.seed["START"].id),
                    "name": "开始",
                    "config": {},
                    "position": {"x": 100, "y": 100},
                },
                {
                    "id": str(approval_id),
                    "node_definition_id": str(self.seed["APPROVAL"].id),
                    "name": "财务审批",
                    "config": {
                        "approval_mode": "AND",
                        "approvers": [{"person_id": str(self.person_id)}],
                    },
                    "position": {"x": 300, "y": 100},
                },
                {
                    "id": str(end_id),
                    "node_definition_id": str(self.seed["END"].id),
                    "name": "结束",
                    "config": {},
                    "position": {"x": 500, "y": 100},
                },
            ],
            "orchestration": {
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
        }

    def test_admin_key_is_required(self) -> None:
        """缺少管理密钥时拒绝访问。"""

        response = self.client.get("/api/admin/processes")
        self.assertEqual(response.status_code, 401)

    def test_create_save_publish_and_create_next_draft(self) -> None:
        """验证从 V1 草稿到发布再到 V2 草稿的完整接口链路。"""

        process_id, v1_id = self.create_process()
        save_response = self.client.put(
            f"/api/admin/process-versions/{v1_id}/graph",
            headers=self.admin_headers,
            json=self.build_graph_payload(revision=0),
        )
        self.assertEqual(save_response.status_code, 200, save_response.text)
        self.assertEqual(save_response.json()["data"]["revision"], 1)

        publish_response = self.client.post(
            f"/api/admin/process-versions/{v1_id}/publish",
            headers=self.admin_headers,
        )
        self.assertEqual(publish_response.status_code, 200, publish_response.text)
        published = publish_response.json()["data"]
        self.assertEqual(published["status"], "ENABLED")
        self.assertEqual(published["current_version_id"], v1_id)
        self.assertIsNone(published["draft_version_id"])

        draft_response = self.client.post(
            f"/api/admin/processes/{process_id}/draft",
            headers=self.admin_headers,
        )
        self.assertEqual(draft_response.status_code, 201, draft_response.text)
        self.assertEqual(draft_response.json()["data"]["version_no"], 2)
        self.assertEqual(draft_response.json()["data"]["status"], "DRAFT")

    def test_published_version_is_read_only(self) -> None:
        """已发布版本再次保存返回 409。"""

        _, version_id = self.create_process()
        self.client.put(
            f"/api/admin/process-versions/{version_id}/graph",
            headers=self.admin_headers,
            json=self.build_graph_payload(revision=0),
        )
        self.client.post(
            f"/api/admin/process-versions/{version_id}/publish",
            headers=self.admin_headers,
        )

        response = self.client.put(
            f"/api/admin/process-versions/{version_id}/graph",
            headers=self.admin_headers,
            json=self.build_graph_payload(revision=1),
        )
        self.assertEqual(response.status_code, 409)

    def test_stale_revision_returns_409(self) -> None:
        """旧 revision 不能覆盖已经保存的新草稿。"""

        _, version_id = self.create_process()
        first_payload = self.build_graph_payload(revision=0, name="第一次保存")
        first_response = self.client.put(
            f"/api/admin/process-versions/{version_id}/graph",
            headers=self.admin_headers,
            json=first_payload,
        )
        self.assertEqual(first_response.status_code, 200)

        stale_response = self.client.put(
            f"/api/admin/process-versions/{version_id}/graph",
            headers=self.admin_headers,
            json=self.build_graph_payload(revision=0, name="过期保存"),
        )
        self.assertEqual(stale_response.status_code, 409)

    def test_version_list_and_graph_read(self) -> None:
        """版本列表和版本整图返回明确的版本信息。"""

        process_id, version_id = self.create_process()
        self.client.put(
            f"/api/admin/process-versions/{version_id}/graph",
            headers=self.admin_headers,
            json=self.build_graph_payload(revision=0),
        )

        versions_response = self.client.get(
            f"/api/admin/processes/{process_id}/versions",
            headers=self.admin_headers,
        )
        self.assertEqual(versions_response.status_code, 200)
        versions = versions_response.json()["data"]
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]["id"], version_id)
        self.assertEqual(versions[0]["node_count"], 3)

        graph_response = self.client.get(
            f"/api/admin/process-versions/{version_id}/graph",
            headers=self.admin_headers,
        )
        self.assertEqual(graph_response.status_code, 200)
        graph = graph_response.json()["data"]
        self.assertEqual(graph["version_id"], version_id)
        self.assertEqual(graph["version_no"], 1)
        self.assertEqual(len(graph["nodes"]), 3)

    def test_invalid_graph_returns_structured_422(self) -> None:
        """非法整图返回结构化校验问题。"""

        _, version_id = self.create_process()
        payload = self.build_graph_payload(revision=0)
        payload["orchestration"] = {"connections": []}
        response = self.client.put(
            f"/api/admin/process-versions/{version_id}/graph",
            headers=self.admin_headers,
            json=payload,
        )

        self.assertEqual(response.status_code, 422)
        self.assertTrue(response.json()["detail"]["issues"])


if __name__ == "__main__":
    unittest.main()
