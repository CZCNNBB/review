"""通用 HTTP 执行器测试。

覆盖请求构造、成功状态码规则、超时、网络异常、响应截断，以及 Service Token 不进入
执行结果。
"""

import json
import unittest
from uuid import uuid4

import httpx

from app.common.scope import CallbackTarget
from app.server.process.src.constants import (
    EXECUTION_STATUS_FAILED,
    EXECUTION_STATUS_SUCCEEDED,
    MAX_RESPONSE_BODY_BYTES,
)
from app.server.process.src.execution.executor import (
    BusinessActionExecutor,
    is_success_status,
)
from app.server.process.src.models.execution_model import BusinessExecutionRecord


SERVICE_TOKEN = "service_token_super_secret_value"


class ExecutionExecutorTestCase(unittest.TestCase):
    """验证执行器的请求构造和结果判定。"""

    def setUp(self) -> None:
        """准备回调目标和捕获请求的 MockTransport 客户端。"""

        self.captured_requests: list[httpx.Request] = []
        self.engine_headers = {
            "Authorization": f"Bearer {SERVICE_TOKEN}",
        }
        self.target = CallbackTarget(
            tenant_id=uuid4(),
            base_url="https://finance.example.com/internal/approval/",
            header_name="Authorization",
            token_prefix="Bearer",
            token=SERVICE_TOKEN,
        )

    def build_executor(self, handler) -> BusinessActionExecutor:
        """用 MockTransport 构造执行器，避免真实网络请求。"""

        def capture_handler(request: httpx.Request) -> httpx.Response:
            self.captured_requests.append(request)
            return handler(request)

        self.client = httpx.Client(transport=httpx.MockTransport(capture_handler))
        self.addCleanup(self.client.close)
        return BusinessActionExecutor(client=self.client)

    def build_record(
        self,
        http_method: str = "POST",
        relative_path: str = "/payment/execute",
        success_status_codes: list[int] | None = None,
        timeout_ms: int = 5000,
        request_payload: dict | None = None,
    ) -> BusinessExecutionRecord:
        """构造一条待执行的记录快照。"""

        return BusinessExecutionRecord(
            approval_instance_id=uuid4(),
            action_code="PAYMENT_EXECUTE",
            http_method=http_method,
            relative_path=relative_path,
            success_status_codes_json=success_status_codes,
            timeout_ms=timeout_ms,
            request_payload_json=request_payload or {"payment_id": "PAY-001"},
        )

    # ------------------------------------------------------------------
    # 成功判定
    # ------------------------------------------------------------------

    def test_success_status_rule(self) -> None:
        """没有配置状态码时全部 2xx 成功，配置后只认命中的状态码。"""

        self.assertTrue(is_success_status(200, None))
        self.assertTrue(is_success_status(204, []))
        self.assertFalse(is_success_status(301, []))
        self.assertFalse(is_success_status(404, None))
        # 配置了状态码后只有列表内的取值才算成功。
        self.assertTrue(is_success_status(202, [200, 202]))
        self.assertFalse(is_success_status(204, [200, 202]))
        self.assertFalse(is_success_status(500, [200, 202]))

    def test_two_hundred_response_succeeds(self) -> None:
        """2xx 响应判为成功并保存响应正文。"""

        executor = self.build_executor(
            lambda request: httpx.Response(200, json={"ok": True})
        )

        outcome = executor.execute(self.build_record(), self.target)

        self.assertEqual(outcome.status, EXECUTION_STATUS_SUCCEEDED)
        self.assertEqual(outcome.http_status_code, 200)
        self.assertEqual(json.loads(outcome.response_body), {"ok": True})
        self.assertIsNone(outcome.error_message)

    def test_configured_status_code_is_required(self) -> None:
        """配置了成功状态码后，未命中的 2xx 也算失败。"""

        executor = self.build_executor(lambda request: httpx.Response(204))

        outcome = executor.execute(
            self.build_record(success_status_codes=[200]),
            self.target,
        )

        self.assertEqual(outcome.status, EXECUTION_STATUS_FAILED)
        self.assertEqual(outcome.http_status_code, 204)
        self.assertIn("204", outcome.error_message)

    def test_configured_status_code_succeeds(self) -> None:
        """命中配置的成功状态码时判为成功。"""

        executor = self.build_executor(lambda request: httpx.Response(202))

        outcome = executor.execute(
            self.build_record(success_status_codes=[200, 202]),
            self.target,
        )

        self.assertEqual(outcome.status, EXECUTION_STATUS_SUCCEEDED)
        self.assertEqual(outcome.http_status_code, 202)

    def test_error_status_code_fails_with_body(self) -> None:
        """非成功状态码判为失败，并保留响应正文供后台核对。"""

        executor = self.build_executor(
            lambda request: httpx.Response(500, text="business failure")
        )

        outcome = executor.execute(self.build_record(), self.target)

        self.assertEqual(outcome.status, EXECUTION_STATUS_FAILED)
        self.assertEqual(outcome.http_status_code, 500)
        self.assertEqual(outcome.response_body, "business failure")

    # ------------------------------------------------------------------
    # 异常
    # ------------------------------------------------------------------

    def test_timeout_is_reported_as_failure(self) -> None:
        """超时判为失败，不留下响应状态码。"""

        def raise_timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        executor = self.build_executor(raise_timeout)

        outcome = executor.execute(
            self.build_record(timeout_ms=1500),
            self.target,
        )

        self.assertEqual(outcome.status, EXECUTION_STATUS_FAILED)
        self.assertIsNone(outcome.http_status_code)
        self.assertIn("超时", outcome.error_message)

    def test_network_error_is_reported_as_failure(self) -> None:
        """网络异常判为失败，并保留已经组成的请求地址。"""

        def raise_connect_error(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        executor = self.build_executor(raise_connect_error)

        outcome = executor.execute(self.build_record(), self.target)

        self.assertEqual(outcome.status, EXECUTION_STATUS_FAILED)
        self.assertIsNone(outcome.http_status_code)
        self.assertIn("无法连接业务系统", outcome.error_message)
        self.assertEqual(
            outcome.request_url,
            "https://finance.example.com/internal/approval/payment/execute",
        )

    # ------------------------------------------------------------------
    # 请求构造与敏感信息
    # ------------------------------------------------------------------

    def test_request_uses_snapshot_configuration_and_tenant_credentials(self) -> None:
        """请求方法、地址和请求体来自快照，认证头来自租户配置。"""

        executor = self.build_executor(lambda request: httpx.Response(200))

        outcome = executor.execute(
            self.build_record(
                http_method="PATCH",
                relative_path="/payment/execute",
                request_payload={"payment_id": "PAY-002", "amount": 100},
            ),
            self.target,
        )

        self.assertEqual(len(self.captured_requests), 1)
        request = self.captured_requests[0]
        self.assertEqual(request.method, "PATCH")
        # 基础地址末尾斜杠与相对路径开头的斜杠不能拼成双斜杠。
        self.assertEqual(
            str(request.url),
            "https://finance.example.com/internal/approval/payment/execute",
        )
        self.assertEqual(request.headers["Authorization"], f"Bearer {SERVICE_TOKEN}")
        self.assertEqual(
            json.loads(request.content),
            {"payment_id": "PAY-002", "amount": 100},
        )
        self.assertEqual(
            outcome.request_url,
            "https://finance.example.com/internal/approval/payment/execute",
        )

    def test_empty_token_prefix_sends_raw_token(self) -> None:
        """前缀为空时认证头直接放 Token 明文，适配不使用 Bearer 的业务系统。"""

        executor = self.build_executor(lambda request: httpx.Response(200))
        target = CallbackTarget(
            tenant_id=uuid4(),
            base_url="https://contract.example.com",
            header_name="X-Token",
            token_prefix="",
            token=SERVICE_TOKEN,
        )

        executor.execute(self.build_record(), target)

        self.assertEqual(self.captured_requests[0].headers["X-Token"], SERVICE_TOKEN)

    def test_service_token_never_appears_in_outcome(self) -> None:
        """执行结果里不能出现 Service Token，失败摘要也不能带出认证头。"""

        def raise_connect_error(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        failing_executor = self.build_executor(raise_connect_error)
        failed_outcome = failing_executor.execute(self.build_record(), self.target)

        self.assertNotIn(SERVICE_TOKEN, failed_outcome.error_message)
        self.assertNotIn("Bearer", failed_outcome.error_message)
        self.assertIsNone(failed_outcome.response_body)

        success_executor = self.build_executor(
            lambda request: httpx.Response(200, text="ok")
        )
        success_outcome = success_executor.execute(self.build_record(), self.target)

        self.assertNotIn(SERVICE_TOKEN, success_outcome.response_body)
        self.assertNotIn(SERVICE_TOKEN, str(success_outcome))

    # ------------------------------------------------------------------
    # 响应截断
    # ------------------------------------------------------------------

    def test_long_response_body_is_truncated_to_utf8_limit(self) -> None:
        """超长响应正文按 UTF-8 字节上限截断后保存。"""

        executor = self.build_executor(
            lambda request: httpx.Response(200, text="x" * (MAX_RESPONSE_BODY_BYTES * 3))
        )

        outcome = executor.execute(self.build_record(), self.target)

        self.assertEqual(outcome.status, EXECUTION_STATUS_SUCCEEDED)
        self.assertEqual(
            len(outcome.response_body.encode("utf-8")),
            MAX_RESPONSE_BODY_BYTES,
        )
        self.assertTrue(outcome.response_body.endswith("…"))

    def test_multibyte_response_body_is_truncated_without_broken_characters(self) -> None:
        """中文正文同样按字节上限截断，且不能截断在多字节字符中间。"""

        executor = self.build_executor(
            lambda request: httpx.Response(
                200,
                text="付款失败原因说明" * 1000,
            )
        )

        outcome = executor.execute(self.build_record(), self.target)

        self.assertEqual(outcome.status, EXECUTION_STATUS_SUCCEEDED)
        # 结果必须能重新编码成合法 UTF-8，不含被切开的半个字符。
        self.assertLessEqual(
            len(outcome.response_body.encode("utf-8")),
            MAX_RESPONSE_BODY_BYTES,
        )
        outcome.response_body.encode("utf-8").decode("utf-8")
        self.assertTrue(outcome.response_body.endswith("…"))

    def test_long_error_message_is_truncated(self) -> None:
        """超长失败摘要按字符数上限截断。"""

        executor = self.build_executor(
            lambda request: httpx.Response(200)
        )

        outcome = executor.execute(
            self.build_record(success_status_codes=[201]),
            self.target,
        )

        self.assertLessEqual(len(outcome.error_message), 1000)


if __name__ == "__main__":
    unittest.main()
