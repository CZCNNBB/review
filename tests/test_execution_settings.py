"""业务执行 Worker 的环境配置校验测试。

轮询频率、领取数量和并发数必须通过环境变量配置。配置不合法时应用要在启动阶段失败，
不能带着错误的参数静默运行。
"""

import os
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet

from app.server.process.src.constants import (
    ENV_BATCH_SIZE,
    ENV_CONCURRENCY,
    ENV_POLL_INTERVAL_SECONDS,
    ENV_WORKER_ENABLED,
)
from app.server.process.src.execution.bootstrap import (
    BusinessExecutionStartupError,
    start_business_execution_worker,
)
from app.server.process.src.execution.settings import (
    ExecutionWorkerConfigError,
    ExecutionWorkerSettings,
)


class ExecutionWorkerSettingsTestCase(unittest.TestCase):
    """验证环境变量读取、默认值和非法取值提示。"""

    def test_defaults_are_used_when_nothing_is_configured(self) -> None:
        """没有配置任何环境变量时使用第一版默认值。"""

        settings = ExecutionWorkerSettings.from_environment({})

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.poll_interval_seconds, 2.0)
        self.assertEqual(settings.batch_size, 10)
        self.assertEqual(settings.concurrency, 5)

    def test_configured_values_are_read(self) -> None:
        """显式配置的取值会被读取，空白字符串按未配置处理。"""

        settings = ExecutionWorkerSettings.from_environment(
            {
                ENV_WORKER_ENABLED: "false",
                ENV_POLL_INTERVAL_SECONDS: "0.5",
                ENV_BATCH_SIZE: "20",
                ENV_CONCURRENCY: "3",
            }
        )

        self.assertFalse(settings.enabled)
        self.assertEqual(settings.poll_interval_seconds, 0.5)
        self.assertEqual(settings.batch_size, 20)
        self.assertEqual(settings.concurrency, 3)

        blank_settings = ExecutionWorkerSettings.from_environment(
            {ENV_POLL_INTERVAL_SECONDS: "   "}
        )
        self.assertEqual(blank_settings.poll_interval_seconds, 2.0)

    def test_invalid_boolean_is_rejected(self) -> None:
        """启用开关只接受明确的布尔写法。"""

        with self.assertRaises(ExecutionWorkerConfigError) as context:
            ExecutionWorkerSettings.from_environment({ENV_WORKER_ENABLED: "maybe"})

        self.assertIn(ENV_WORKER_ENABLED, str(context.exception))

    def test_poll_interval_must_be_greater_than_zero(self) -> None:
        """轮询间隔必须大于 0。"""

        for invalid_value in ("0", "-1", "abc"):
            with self.subTest(value=invalid_value):
                with self.assertRaises(ExecutionWorkerConfigError) as context:
                    ExecutionWorkerSettings.from_environment(
                        {ENV_POLL_INTERVAL_SECONDS: invalid_value}
                    )
                self.assertIn(ENV_POLL_INTERVAL_SECONDS, str(context.exception))

    def test_batch_size_must_be_positive_integer(self) -> None:
        """批量数量必须是正整数。"""

        for invalid_value in ("0", "-5", "1.5", ""):
            if invalid_value == "":
                continue
            with self.subTest(value=invalid_value):
                with self.assertRaises(ExecutionWorkerConfigError) as context:
                    ExecutionWorkerSettings.from_environment(
                        {ENV_BATCH_SIZE: invalid_value}
                    )
                self.assertIn(ENV_BATCH_SIZE, str(context.exception))

    def test_concurrency_must_be_positive_integer(self) -> None:
        """并发数必须是正整数。"""

        for invalid_value in ("0", "-3", "two"):
            with self.subTest(value=invalid_value):
                with self.assertRaises(ExecutionWorkerConfigError) as context:
                    ExecutionWorkerSettings.from_environment(
                        {ENV_CONCURRENCY: invalid_value}
                    )
                self.assertIn(ENV_CONCURRENCY, str(context.exception))

    def test_concurrency_cannot_exceed_batch_size(self) -> None:
        """并发数不能超过单批领取数量。"""

        with self.assertRaises(ExecutionWorkerConfigError) as context:
            ExecutionWorkerSettings.from_environment(
                {
                    ENV_BATCH_SIZE: "3",
                    ENV_CONCURRENCY: "4",
                }
            )

        self.assertIn(ENV_CONCURRENCY, str(context.exception))
        self.assertIn(ENV_BATCH_SIZE, str(context.exception))


class BusinessExecutionStartupTestCase(unittest.TestCase):
    """验证应用启动阶段的配置校验行为。"""

    def test_invalid_configuration_fails_startup(self) -> None:
        """环境变量非法时启动失败并给出明确提示。"""

        with patch.dict(os.environ, {ENV_BATCH_SIZE: "0"}, clear=False):
            with self.assertRaises(BusinessExecutionStartupError) as context:
                start_business_execution_worker()

        self.assertIn(ENV_BATCH_SIZE, str(context.exception))

    def test_disabled_worker_does_not_require_master_key(self) -> None:
        """停用 Worker 时不要求配置 Service Token 加密主密钥。"""

        environment = {
            ENV_WORKER_ENABLED: "false",
            "APPROVAL_CREDENTIAL_MASTER_KEY": "",
        }
        with patch.dict(os.environ, environment, clear=False):
            self.assertIsNone(start_business_execution_worker())

    def test_missing_master_key_fails_startup(self) -> None:
        """启用 Worker 时必须配置可用的 Service Token 加密主密钥。"""

        environment = {
            ENV_WORKER_ENABLED: "true",
            "APPROVAL_CREDENTIAL_MASTER_KEY": "",
        }
        with patch.dict(os.environ, environment, clear=False):
            with self.assertRaises(BusinessExecutionStartupError) as context:
                start_business_execution_worker()

        self.assertIn("APPROVAL_CREDENTIAL_MASTER_KEY", str(context.exception))

    def test_invalid_master_key_format_fails_startup(self) -> None:
        """主密钥格式非法时同样在启动阶段失败。"""

        environment = {
            ENV_WORKER_ENABLED: "true",
            "APPROVAL_CREDENTIAL_MASTER_KEY": "not-a-fernet-key",
        }
        with patch.dict(os.environ, environment, clear=False):
            with self.assertRaises(BusinessExecutionStartupError):
                start_business_execution_worker()

    def test_valid_master_key_starts_and_stops_worker(self) -> None:
        """配置合法时 Worker 可以启动，并能被有序停止。"""

        environment = {
            ENV_WORKER_ENABLED: "true",
            "APPROVAL_CREDENTIAL_MASTER_KEY": Fernet.generate_key().decode("utf-8"),
            ENV_POLL_INTERVAL_SECONDS: "30",
        }
        with patch.dict(os.environ, environment, clear=False):
            worker = start_business_execution_worker()

        self.assertIsNotNone(worker)
        try:
            # 重复启动不会创建第二个轮询循环。
            worker.start()
        finally:
            worker.stop(timeout_seconds=5)


if __name__ == "__main__":
    unittest.main()
