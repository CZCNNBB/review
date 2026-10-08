"""假业务系统的页面与本地 HTTP 闭环测试，不连接真实审批中心或 OSS。"""

import argparse
import io
import json
import shutil
import subprocess
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import httpx
from python_multipart import parse_form

from test_backcall import test_backcall


class BackcallPageTestCase(unittest.TestCase):
    """验证用户直接点击联调页面按钮时附件不会被遗漏。"""

    def test_page_attachment_actions(self) -> None:
        """用现有前端 jsdom 依赖运行真实页面脚本，无须启动云存储。"""

        backend_root = Path(__file__).resolve().parents[1]
        node = shutil.which("node")
        jsdom = backend_root / "web-vue" / "node_modules" / "jsdom"
        if not node or not jsdom.exists():
            self.skipTest("页面检查需要 Node.js 和已安装的前端 jsdom 依赖")
        page = test_backcall.PAGE.replace("__CONFIG__", "{}")
        result = subprocess.run(
            [node, str(backend_root / "tests" / "test_backcall_page.cjs")],
            input=page,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=30,
            cwd=backend_root,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class BackcallFlowTestCase(unittest.TestCase):
    """验证业务方批量上传、发起审批、查询详情与接收回调。"""

    def setUp(self) -> None:
        """在本机启动两个临时 HTTP 服务，分别扮演审批中心和业务系统。"""

        self.center_requests: dict[str, object] = {}
        self.file_ids = [str(uuid4()), str(uuid4())]
        self.instance_id = str(uuid4())
        state = self

        class CenterHandler(BaseHTTPRequestHandler):
            """仅实现测试闭环需要的三个审批中心接口。"""

            def do_POST(self) -> None:  # noqa: N802
                """接收文件或审批请求，记录业务方实际发送的内容。"""

                if self.path == "/api/files":
                    uploads = []

                    def collect_file(uploaded):
                        """记录转发后的文件名与内容，解析完成后再关闭文件。"""

                        uploaded.file_object.seek(0)
                        uploads.append(
                            (
                                uploaded.file_name.decode("utf-8"),
                                uploaded.file_object.read(),
                            )
                        )
                        parsed_files.append(uploaded)

                    parsed_files = []
                    parse_form(
                        {
                            "Content-Type": self.headers["Content-Type"].encode("ascii"),
                            "Content-Length": self.headers["Content-Length"].encode("ascii"),
                        },
                        self.rfile,
                        None,
                        collect_file,
                    )
                    for uploaded in parsed_files:
                        uploaded.close()
                    state.center_requests["uploads"] = uploads
                    state.center_requests["upload_key"] = self.headers.get("X-API-Key")
                    if any(name.endswith(".exe") for name, _ in uploads):
                        self._json(422, {"detail": "files[1]：文件类型不受支持"})
                        return
                    files = [
                        {
                            "file_id": state.file_ids[index],
                            "file_name": name,
                            "size_bytes": len(content),
                        }
                        for index, (name, content) in enumerate(uploads)
                    ]
                    self._json(201, {"code": 0, "data": {"file_ids": state.file_ids, "files": files}})
                    return

                length = int(self.headers.get("Content-Length", "0"))
                approval = json.loads(self.rfile.read(length))
                state.center_requests["approval"] = approval
                if any(file_id not in state.file_ids for file_id in approval.get("file_ids", [])):
                    self._json(422, {"detail": "file_id 不存在"})
                    return
                self._json(
                    201,
                    {
                        "code": 0,
                        "data": {
                            "instance_id": state.instance_id,
                            "status": "RUNNING",
                            "current_node_name": "财务审批",
                            "pending_approver_person_ids": [],
                        },
                    },
                )

            def do_GET(self) -> None:  # noqa: N802
                """返回附带两个文件和审批意见的实例详情。"""

                self._json(
                    200,
                    {
                        "code": 0,
                        "data": {
                            "id": state.instance_id,
                            "status": "APPROVED",
                            "current_node": None,
                            "attachments": [
                                {"file_id": file_id, "file_name": name}
                                for file_id, name in zip(state.file_ids, ["合同.pdf", "凭证.png"])
                            ],
                            "pending_tasks": [],
                            "timeline_entries": [
                                {
                                    "node_execution": {"node_name": "财务审批", "status": "COMPLETED"},
                                    "records": [{"action": "APPROVE", "comment": "同意"}],
                                }
                            ],
                        },
                    },
                )

            def _json(self, status: int, body: dict) -> None:
                """为假审批中心返回标准 JSON 响应。"""

                raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                """关闭测试服务的访问日志。"""

        self.center = ThreadingHTTPServer(("127.0.0.1", 0), CenterHandler)
        center_address = f"http://127.0.0.1:{self.center.server_port}"
        options = argparse.Namespace(
            center=center_address,
            api_key="test-tenant-key",
            process_id=str(uuid4()),
            action_code="PAYMENT_EXECUTE",
            admin_key="",
            host="127.0.0.1",
            port=0,
            pay_path="/pay",
            status=200,
            delay=0,
            token_header="X-Service-Token",
            expect_token="super-secret-token",
        )
        self.business = ThreadingHTTPServer(
            ("127.0.0.1", 0), test_backcall.make_handler(options)
        )
        self.base = f"http://127.0.0.1:{self.business.server_port}"
        self.threads = [
            threading.Thread(target=server.serve_forever, daemon=True)
            for server in (self.center, self.business)
        ]
        for thread in self.threads:
            thread.start()
        with test_backcall.COUNT_LOCK:
            test_backcall.EVENTS.clear()
            test_backcall.COUNT = 0

    def tearDown(self) -> None:
        """停止两个临时服务并等待线程退出。"""

        for server in (self.business, self.center):
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join(timeout=2)

    def test_upload_start_detail_and_callback(self) -> None:
        """文件 ID 只进入审批顶层，详情保留附件，回调只携带业务数据。"""

        with httpx.Client(timeout=10) as client:
            page = client.get(self.base)
            self.assertEqual(page.status_code, 200)
            self.assertIn("批量上传附件", page.text)
            self.assertNotIn("test-tenant-key", page.text)
            self.assertNotIn("super-secret-token", page.text)

            upload = client.post(
                f"{self.base}/_upload",
                files=[
                    ("files", ("合同.pdf", b"%PDF-1.7\ncontract", "application/pdf")),
                    ("files", ("凭证.png", b"\x89PNG\r\n\x1a\nimage", "image/png")),
                ],
            )
            self.assertEqual(upload.status_code, 200, upload.text)
            self.assertEqual(upload.json()["file_ids"], self.file_ids)
            self.assertEqual(self.center_requests["upload_key"], "test-tenant-key")

            started = client.post(
                f"{self.base}/start",
                json={"payment_id": "PAY-001", "JinEr": 500, "file_ids": self.file_ids},
            )
            self.assertEqual(started.status_code, 200, started.text)
            approval = self.center_requests["approval"]
            self.assertEqual(approval["file_ids"], self.file_ids)
            self.assertEqual(approval["approval_form"], {"JinEr": 500})
            self.assertEqual(approval["execution_payload"], {"payment_id": "PAY-001", "JinEr": 500})

            detail = client.get(f"{self.base}/_status", params={"instance_id": self.instance_id})
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(
                [file["file_id"] for file in detail.json()["attachments"]],
                self.file_ids,
            )
            self.assertEqual(detail.json()["timeline_entries"][0]["records"][0]["comment"], "同意")

            callback_log = io.StringIO()
            with redirect_stdout(callback_log):
                callback = client.post(
                    f"{self.base}/pay",
                    headers={"X-Service-Token": "Bearer super-secret-token"},
                    json={"payment_id": "PAY-001", "JinEr": 500},
                )
            self.assertEqual(callback.status_code, 200)
            self.assertNotIn("super-secret-token", callback_log.getvalue())
            events = client.get(f"{self.base}/_events").json()
            self.assertEqual(events["count"], 1)
            self.assertTrue(events["events"][0]["token_ok"])
            self.assertEqual(events["events"][0]["body"]["payment_id"], "PAY-001")

    def test_invalid_file_and_reference_show_errors(self) -> None:
        """文件类型和无效 file_id 的错误会原样提示，不返回成功实例。"""

        with httpx.Client(timeout=10) as client:
            upload = client.post(
                f"{self.base}/_upload",
                files=[
                    ("files", ("合同.pdf", b"%PDF-1.7\ncontract", "application/pdf")),
                    ("files", ("program.exe", b"MZ", "application/octet-stream")),
                ],
            )
            self.assertEqual(upload.status_code, 422)
            self.assertFalse(upload.json()["ok"])
            self.assertIn("files[1]", upload.json()["msg"])

            started = client.post(
                f"{self.base}/start",
                json={"payment_id": "PAY-BAD", "JinEr": 500, "file_ids": [str(uuid4())]},
            )
            self.assertEqual(started.status_code, 422)
            self.assertFalse(started.json()["ok"])
            self.assertIn("file_id 不存在", started.json()["msg"])

            status = client.get(f"{self.base}/_status", params={"instance_id": "not-a-uuid"})
            self.assertEqual(status.status_code, 400)


if __name__ == "__main__":
    unittest.main()
