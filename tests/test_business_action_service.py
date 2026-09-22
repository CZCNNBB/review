"""业务动作定义与执行参数规则测试，不需要数据库连接。

覆盖回调地址安全规则、调用方法限制、请求参数 Schema 自身的合法性和执行参数校验的
字段路径，这些规则直接决定业务系统能否绕过租户登记的回调地址。
"""

import unittest

from pydantic import ValidationError

from app.server.integration.src.models.business_action_model import BusinessAction
from app.server.integration.src.schemas.business_action_schema import (
    BusinessActionCreateRequest,
    BusinessActionUpdateRequest,
)
from app.server.integration.src.service.business_action_service import (
    BusinessActionService,
)
from app.server.integration.src.service.exceptions import (
    BusinessActionValidationError,
)


PAYMENT_SCHEMA = {
    "type": "object",
    "required": ["payment_id", "amount"],
    "properties": {
        "payment_id": {"type": "string", "minLength": 1},
        "amount": {"type": "number", "exclusiveMinimum": 0},
    },
    "additionalProperties": False,
}


def build_action(request_schema: dict | None = None) -> BusinessAction:
    """构造一个不落库的业务动作，用于测试校验规则。"""

    return BusinessAction(
        action_code="PAYMENT_EXECUTE",
        name="执行付款",
        http_method="POST",
        relative_path="/payments/execute",
        request_schema_json=request_schema if request_schema is not None else PAYMENT_SCHEMA,
        success_status_codes_json=[],
        timeout_ms=5000,
    )


class BusinessActionRequestTestCase(unittest.TestCase):
    """验证业务动作请求模型的地址与调用方法规则。"""

    def test_relative_path_must_start_with_single_slash(self) -> None:
        """相对路径必须以单个斜杠开头，不能是协议相对地址。"""

        for invalid_path in ("payments/execute", "//evil.example.com/pay", ""):
            with self.assertRaises(ValidationError, msg=invalid_path):
                BusinessActionCreateRequest(
                    action_code="PAYMENT_EXECUTE",
                    name="执行付款",
                    relative_path=invalid_path,
                )

        request = BusinessActionCreateRequest(
            action_code="PAYMENT_EXECUTE",
            name="执行付款",
            relative_path="/payments/execute",
        )
        self.assertEqual(request.relative_path, "/payments/execute")

    def test_relative_path_cannot_be_full_url(self) -> None:
        """相对路径不能保存完整 URL，避免业务请求绕过租户登记的回调地址。"""

        with self.assertRaises(ValidationError):
            BusinessActionCreateRequest(
                action_code="PAYMENT_EXECUTE",
                name="执行付款",
                relative_path="/redirect?to=https://evil.example.com/pay",
            )

    def test_http_method_is_limited_to_first_version_support(self) -> None:
        """第一版只允许 POST、PUT、PATCH，方法名统一转大写。"""

        request = BusinessActionCreateRequest(
            action_code="PAYMENT_EXECUTE",
            name="执行付款",
            relative_path="/payments/execute",
            http_method="patch",
        )
        self.assertEqual(request.http_method, "PATCH")

        for unsupported_method in ("GET", "DELETE", "HEAD"):
            with self.assertRaises(ValidationError, msg=unsupported_method):
                BusinessActionCreateRequest(
                    action_code="PAYMENT_EXECUTE",
                    name="执行付款",
                    relative_path="/payments/execute",
                    http_method=unsupported_method,
                )

    def test_action_code_is_normalized_to_uppercase(self) -> None:
        """业务动作标识统一大写，避免只差大小写的重复动作。"""

        request = BusinessActionCreateRequest(
            action_code="payment_execute",
            name="执行付款",
            relative_path="/payments/execute",
        )
        self.assertEqual(request.action_code, "PAYMENT_EXECUTE")

    def test_success_status_codes_are_deduplicated_and_sorted(self) -> None:
        """成功状态码去重升序保存，越界状态码被拒绝。"""

        request = BusinessActionCreateRequest(
            action_code="PAYMENT_EXECUTE",
            name="执行付款",
            relative_path="/payments/execute",
            success_status_codes=[204, 200, 200],
        )
        self.assertEqual(request.success_status_codes, [200, 204])

        with self.assertRaises(ValidationError):
            BusinessActionCreateRequest(
                action_code="PAYMENT_EXECUTE",
                name="执行付款",
                relative_path="/payments/execute",
                success_status_codes=[2000],
            )

    def test_update_request_rejects_empty_body(self) -> None:
        """更新请求至少要提供一个字段。"""

        with self.assertRaises(ValidationError):
            BusinessActionUpdateRequest()


class BusinessActionSchemaValidationTestCase(unittest.TestCase):
    """验证业务动作请求参数 Schema 自身的合法性。"""

    def test_request_schema_root_type_must_be_object(self) -> None:
        """请求参数 Schema 的根类型必须是 object。"""

        service = BusinessActionService()
        action = build_action({"type": "array", "items": {"type": "string"}})

        with self.assertRaises(BusinessActionValidationError):
            service.validate_execution_payload(action, {})

        self.assertEqual(
            service._normalize_request_schema({"type": "object"}),
            {"type": "object"},
        )

    def test_invalid_request_schema_is_rejected_before_saving(self) -> None:
        """非法的 JSON Schema 不允许落库，否则之后每次校验都会失败。"""

        service = BusinessActionService()

        with self.assertRaises(BusinessActionValidationError):
            service._normalize_request_schema({"type": "object", "properties": "非法"})

    def test_empty_request_schema_means_no_payload_rule(self) -> None:
        """未配置请求参数 Schema 时不校验执行参数。"""

        service = BusinessActionService()
        service.validate_execution_payload(build_action({}), {"任意字段": 1})


class ExecutionPayloadValidationTestCase(unittest.TestCase):
    """验证执行参数校验的错误定位能力。"""

    def setUp(self) -> None:
        """准备业务动作服务。"""

        self.service = BusinessActionService()
        self.action = build_action()

    def test_valid_payload_passes(self) -> None:
        """符合请求 Schema 的执行参数可以通过校验。"""

        self.service.validate_execution_payload(
            self.action,
            {"payment_id": "PAY-001", "amount": 100},
        )

    def test_missing_required_field_reports_field_path(self) -> None:
        """缺少必填字段时返回带具体字段路径的 422 问题列表。"""

        with self.assertRaises(BusinessActionValidationError) as context:
            self.service.validate_execution_payload(self.action, {"amount": 100})

        issues = context.exception.issues
        self.assertTrue(issues)
        self.assertEqual(issues[0].field, "execution_payload")
        self.assertIn("payment_id", issues[0].message)

    def test_nested_field_error_reports_full_path(self) -> None:
        """嵌套字段出错时字段路径包含完整的层级。"""

        action = build_action(
            {
                "type": "object",
                "required": ["payment"],
                "properties": {
                    "payment": {
                        "type": "object",
                        "required": ["amount"],
                        "properties": {"amount": {"type": "number"}},
                    }
                },
            }
        )

        with self.assertRaises(BusinessActionValidationError) as context:
            self.service.validate_execution_payload(action, {"payment": {}})

        self.assertEqual(
            [issue.field for issue in context.exception.issues],
            ["execution_payload.payment"],
        )

    def test_unexpected_field_is_rejected(self) -> None:
        """请求 Schema 禁止额外字段时，多余参数会被拒绝。"""

        with self.assertRaises(BusinessActionValidationError) as context:
            self.service.validate_execution_payload(
                self.action,
                {"payment_id": "PAY-001", "amount": 100, "extra": "多余参数"},
            )

        self.assertIn("extra", context.exception.issues[0].message)


if __name__ == "__main__":
    unittest.main()
