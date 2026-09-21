"""审批流管理接口 HTTP 集成测试，需要可用的 PostgreSQL 数据库。"""

import os
import unittest
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.process_test_helpers import (
    DatabaseTestCaseMixin,
    load_seed_node_definitions,
)
from app.common.db.postgres_db import get_postgres_engine
from app.main import create_app
from app.server.organization.src.schemas.organization_schema import PersonCreateRequest
from app.server.organization.src.service.organization_service import OrganizationService


class ProcessApiTestCase(DatabaseTestCaseMixin, unittest.TestCase):
    """验证审批流管理接口的完整链路。"""

    def setUp(self) -> None:
        """准备测试应用、管理密钥和测试人员。"""

        self.previous_admin_key = os.environ.get("APPROVAL_ADMIN_KEY")
        os.environ["APPROVAL_ADMIN_KEY"] = "test-admin-key"
        self.admin_headers = {"X-Admin-Key": "test-admin-key"}

        self.db: Session = self.open_session()
        self.seed = load_seed_node_definitions()

        person = OrganizationService().create_person(
            PersonCreateRequest(name=f"接口测试人员-{uuid4().hex[:8]}"),
            self.db,
        )
        self.track_person(person.id)
        self.person_id = person.id

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

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def create_process(self, name: str | None = None) -> str:
        """通过接口创建流程并登记清理，返回流程 ID。"""

        response = self.client.post(
            "/api/admin/processes",
            headers=self.admin_headers,
            json={
                "name": name or f"接口测试流程-{uuid4().hex[:8]}",
                "form_schema": {
                    "type": "object",
                    "properties": {"amount": {"type": "number"}},
                },
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        process_id = response.json()["data"]["id"]
        self.track_process(UUID(process_id))
        return process_id

    def build_graph_payload(self, process_name: str, **overrides) -> dict:
        """构造最小合法整图保存请求。"""

        start_id, approval_id, end_id = uuid4(), uuid4(), uuid4()
        payload = {
            "name": process_name,
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
                    "config": {"result_status": "APPROVED"},
                    "position": {"x": 500, "y": 100},
                },
            ],
            "orchestration": {
                "connections": [
                    {"source_node_id": str(start_id), "target_node_id": str(approval_id)},
                    {"source_node_id": str(approval_id), "target_node_id": str(end_id)},
                ]
            },
        }
        payload.update(overrides)
        return payload

    # ------------------------------------------------------------------
    # 认证
    # ------------------------------------------------------------------

    def test_admin_key_is_required(self) -> None:
        """缺少管理密钥时拒绝访问。"""

        response = self.client.get("/api/admin/processes")
        self.assertEqual(response.status_code, 401)

    def test_wrong_admin_key_is_rejected(self) -> None:
        """管理密钥错误时拒绝访问。"""

        response = self.client.get(
            "/api/admin/processes",
            headers={"X-Admin-Key": "wrong-key"},
        )
        self.assertEqual(response.status_code, 401)

    def test_missing_admin_key_configuration_returns_503(self) -> None:
        """未配置管理密钥时接口不可用。"""

        os.environ.pop("APPROVAL_ADMIN_KEY", None)
        response = self.client.get("/api/admin/processes", headers=self.admin_headers)
        self.assertEqual(response.status_code, 503)

    # ------------------------------------------------------------------
    # 节点定义接口
    # ------------------------------------------------------------------

    def test_node_definition_crud(self) -> None:
        """节点定义可以创建、列表查询、详情查询和更新。"""

        definition_name = f"接口测试节点-{uuid4().hex[:8]}"
        create_response = self.client.post(
            "/api/admin/node-definitions",
            headers=self.admin_headers,
            json={
                "node_type": "APPROVAL",
                "name": definition_name,
                "config_schema_json": {"type": "object", "properties": {}},
            },
        )
        self.assertEqual(create_response.status_code, 201, create_response.text)
        definition_id = create_response.json()["data"]["id"]
        self.track_node_definition(UUID(definition_id))

        list_response = self.client.get(
            "/api/admin/node-definitions",
            headers=self.admin_headers,
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertIn(
            definition_id,
            [item["id"] for item in list_response.json()["data"]],
        )

        detail_response = self.client.get(
            f"/api/admin/node-definitions/{definition_id}",
            headers=self.admin_headers,
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["data"]["name"], definition_name)

        update_response = self.client.patch(
            f"/api/admin/node-definitions/{definition_id}",
            headers=self.admin_headers,
            json={"status": "DISABLED"},
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["data"]["status"], "DISABLED")

    def test_duplicate_node_definition_name_returns_409(self) -> None:
        """节点定义重名时返回 409。"""

        definition_name = f"重名节点-{uuid4().hex[:8]}"
        first_response = self.client.post(
            "/api/admin/node-definitions",
            headers=self.admin_headers,
            json={"node_type": "APPROVAL", "name": definition_name},
        )
        self.assertEqual(first_response.status_code, 201)
        self.track_node_definition(UUID(first_response.json()["data"]["id"]))

        second_response = self.client.post(
            "/api/admin/node-definitions",
            headers=self.admin_headers,
            json={"node_type": "APPROVAL", "name": definition_name},
        )
        self.assertEqual(second_response.status_code, 409)

    def test_missing_node_definition_returns_404(self) -> None:
        """查询不存在的节点定义返回 404。"""

        response = self.client.get(
            f"/api/admin/node-definitions/{uuid4()}",
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------
    # 流程接口
    # ------------------------------------------------------------------

    def test_missing_process_returns_404(self) -> None:
        """查询不存在的流程返回 404。"""

        response = self.client.get(
            f"/api/admin/processes/{uuid4()}",
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_save_and_read_graph_round_trip(self) -> None:
        """整图保存后读回内容一致。"""

        process_id = self.create_process()
        payload = self.build_graph_payload("整图往返流程")

        save_response = self.client.put(
            f"/api/admin/processes/{process_id}/graph",
            headers=self.admin_headers,
            json=payload,
        )
        self.assertEqual(save_response.status_code, 200, save_response.text)

        graph_response = self.client.get(
            f"/api/admin/processes/{process_id}/graph",
            headers=self.admin_headers,
        )
        self.assertEqual(graph_response.status_code, 200)
        graph = graph_response.json()["data"]

        self.assertEqual(graph["name"], "整图往返流程")
        self.assertEqual(len(graph["nodes"]), 3)
        # 同一批写入的节点 created_at 相同，返回顺序按节点 ID 兜底排序，
        # 因此这里比对集合，顺序稳定性由下面的重复读取断言保证。
        self.assertEqual(
            {node["id"] for node in graph["nodes"]},
            {node["id"] for node in payload["nodes"]},
        )
        self.assertEqual(
            graph["orchestration"]["connections"],
            payload["orchestration"]["connections"],
        )

        # 同一份数据重复读取要返回同样的顺序，前端才能做稳定的差异比对。
        reread_response = self.client.get(
            f"/api/admin/processes/{process_id}/graph",
            headers=self.admin_headers,
        )
        self.assertEqual(
            [node["id"] for node in reread_response.json()["data"]["nodes"]],
            [node["id"] for node in graph["nodes"]],
        )

        # 节点响应带上节点定义信息，画布不必再查一次定义。
        node_types = {node["node_type"] for node in graph["nodes"]}
        self.assertEqual(node_types, {"START", "APPROVAL", "END"})

    def test_invalid_graph_returns_structured_422(self) -> None:
        """非法流程返回 422 并带结构化问题列表。"""

        process_id = self.create_process()
        payload = self.build_graph_payload("非法流程")
        # 去掉全部连线，审批节点没有后续路径。
        payload["orchestration"] = {"connections": []}

        response = self.client.put(
            f"/api/admin/processes/{process_id}/graph",
            headers=self.admin_headers,
            json=payload,
        )
        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        self.assertIn("message", detail)
        self.assertTrue(detail["issues"])
        self.assertIn("code", detail["issues"][0])

    def test_validate_reports_issues_for_saved_definition(self) -> None:
        """校验接口返回 valid 标记和问题列表。"""

        process_id = self.create_process()

        # 还没有节点时校验必然不通过。
        invalid_response = self.client.post(
            f"/api/admin/processes/{process_id}/validate",
            headers=self.admin_headers,
        )
        self.assertEqual(invalid_response.status_code, 200)
        self.assertFalse(invalid_response.json()["data"]["valid"])
        self.assertTrue(invalid_response.json()["data"]["issues"])

        payload = self.build_graph_payload("校验通过流程")
        self.client.put(
            f"/api/admin/processes/{process_id}/graph",
            headers=self.admin_headers,
            json=payload,
        )

        valid_response = self.client.post(
            f"/api/admin/processes/{process_id}/validate",
            headers=self.admin_headers,
        )
        self.assertEqual(valid_response.status_code, 200)
        self.assertTrue(valid_response.json()["data"]["valid"])
        self.assertEqual(valid_response.json()["data"]["issues"], [])

    def test_disabled_node_definition_blocks_save(self) -> None:
        """节点定义停用后引用它的流程无法保存。"""

        definition_name = f"待停用节点-{uuid4().hex[:8]}"
        create_response = self.client.post(
            "/api/admin/node-definitions",
            headers=self.admin_headers,
            json={
                "node_type": "APPROVAL",
                "name": definition_name,
                "config_schema_json": {"type": "object", "properties": {}},
            },
        )
        definition_id = create_response.json()["data"]["id"]
        self.track_node_definition(UUID(definition_id))

        self.client.patch(
            f"/api/admin/node-definitions/{definition_id}",
            headers=self.admin_headers,
            json={"status": "DISABLED"},
        )

        process_id = self.create_process()
        payload = self.build_graph_payload("引用停用定义的流程")
        payload["nodes"][1]["node_definition_id"] = definition_id
        payload["nodes"][1]["config"] = {}

        response = self.client.put(
            f"/api/admin/processes/{process_id}/graph",
            headers=self.admin_headers,
            json=payload,
        )
        self.assertEqual(response.status_code, 422)
        codes = [issue["code"] for issue in response.json()["detail"]["issues"]]
        self.assertIn("NODE_DEFINITION_DISABLED", codes)

    def test_enable_disable_and_copy_flow(self) -> None:
        """启用、停用和复制流程的状态码与状态流转。"""

        process_id = self.create_process()
        payload = self.build_graph_payload("启停测试流程")
        self.client.put(
            f"/api/admin/processes/{process_id}/graph",
            headers=self.admin_headers,
            json=payload,
        )

        enable_response = self.client.post(
            f"/api/admin/processes/{process_id}/enable",
            headers=self.admin_headers,
        )
        self.assertEqual(enable_response.status_code, 200)
        self.assertEqual(enable_response.json()["data"]["status"], "ENABLED")

        copy_response = self.client.post(
            f"/api/admin/processes/{process_id}/copy",
            headers=self.admin_headers,
        )
        self.assertEqual(copy_response.status_code, 201, copy_response.text)
        copied = copy_response.json()["data"]
        self.track_process(UUID(copied["id"]))
        self.assertEqual(copied["status"], "DRAFT")
        self.assertEqual(copied["node_count"], 3)

        disable_response = self.client.post(
            f"/api/admin/processes/{process_id}/disable",
            headers=self.admin_headers,
        )
        self.assertEqual(disable_response.status_code, 200)
        self.assertEqual(disable_response.json()["data"]["status"], "DISABLED")

    def test_disable_draft_returns_409(self) -> None:
        """草稿流程停用返回 409。"""

        process_id = self.create_process()
        response = self.client.post(
            f"/api/admin/processes/{process_id}/disable",
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 409)

    def test_list_processes_includes_node_count(self) -> None:
        """列表返回节点数量。"""

        process_id = self.create_process()
        payload = self.build_graph_payload("列表计数流程")
        self.client.put(
            f"/api/admin/processes/{process_id}/graph",
            headers=self.admin_headers,
            json=payload,
        )

        response = self.client.get(
            "/api/admin/processes",
            headers=self.admin_headers,
            params={"limit": 500},
        )
        self.assertEqual(response.status_code, 200)
        listed = {item["id"]: item for item in response.json()["data"]}
        self.assertEqual(listed[process_id]["node_count"], 3)


if __name__ == "__main__":
    unittest.main()
