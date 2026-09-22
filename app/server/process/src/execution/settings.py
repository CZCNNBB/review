"""业务执行 Worker 的环境配置读取与校验。

轮询频率、领取数量和并发数都不允许写死在代码里。配置不合法时直接让应用启动失败并
说明具体环境变量，不在运行期静默修正，避免部署后发现 Worker 实际按错误的节奏运行。
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass

from app.server.process.src.constants import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_CONCURRENCY,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_WORKER_ENABLED,
    ENV_BATCH_SIZE,
    ENV_CONCURRENCY,
    ENV_POLL_INTERVAL_SECONDS,
    ENV_WORKER_ENABLED,
)


class ExecutionWorkerConfigError(Exception):
    """业务执行 Worker 的环境配置不合法，应用应当启动失败。"""


_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


@dataclass(frozen=True)
class ExecutionWorkerSettings:
    """后台业务执行器一次运行所需的全部参数。"""

    enabled: bool
    poll_interval_seconds: float
    batch_size: int
    concurrency: int

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "ExecutionWorkerSettings":
        """读取环境变量并校验，缺失时使用第一版默认值。"""

        source = os.environ if environ is None else environ

        settings = cls(
            enabled=_read_boolean(
                source,
                ENV_WORKER_ENABLED,
                DEFAULT_WORKER_ENABLED,
            ),
            poll_interval_seconds=_read_positive_float(
                source,
                ENV_POLL_INTERVAL_SECONDS,
                DEFAULT_POLL_INTERVAL_SECONDS,
            ),
            batch_size=_read_positive_int(
                source,
                ENV_BATCH_SIZE,
                DEFAULT_BATCH_SIZE,
            ),
            concurrency=_read_positive_int(
                source,
                ENV_CONCURRENCY,
                DEFAULT_CONCURRENCY,
            ),
        )

        # 一次轮询最多领取 batch_size 条，单进程并发不可能超过领取数量。
        if settings.concurrency > settings.batch_size:
            raise ExecutionWorkerConfigError(
                f"{ENV_CONCURRENCY} 不能大于 {ENV_BATCH_SIZE}："
                f"当前分别为 {settings.concurrency} 和 {settings.batch_size}"
            )
        return settings


def _read_raw_value(source: Mapping[str, str], name: str) -> str | None:
    """读取环境变量原始值，空字符串按未配置处理。"""

    raw_value = source.get(name)
    if raw_value is None:
        return None
    stripped_value = raw_value.strip()
    return stripped_value or None


def _read_boolean(
    source: Mapping[str, str],
    name: str,
    default: bool,
) -> bool:
    """读取布尔开关，取值不在允许范围内时给出明确错误。"""

    raw_value = _read_raw_value(source, name)
    if raw_value is None:
        return default

    normalized_value = raw_value.lower()
    if normalized_value in _TRUE_VALUES:
        return True
    if normalized_value in _FALSE_VALUES:
        return False

    raise ExecutionWorkerConfigError(
        f"{name} 必须是 true 或 false，当前值为 {raw_value}"
    )


def _read_positive_int(
    source: Mapping[str, str],
    name: str,
    default: int,
) -> int:
    """读取正整数配置，非数字或不是正整数时给出明确错误。"""

    raw_value = _read_raw_value(source, name)
    if raw_value is None:
        return default

    try:
        parsed_value = int(raw_value)
    except ValueError as exc:
        raise ExecutionWorkerConfigError(
            f"{name} 必须是正整数，当前值为 {raw_value}"
        ) from exc

    if parsed_value <= 0:
        raise ExecutionWorkerConfigError(
            f"{name} 必须大于 0，当前值为 {raw_value}"
        )
    return parsed_value


def _read_positive_float(
    source: Mapping[str, str],
    name: str,
    default: float,
) -> float:
    """读取正数配置，非数字或不大于零时给出明确错误。"""

    raw_value = _read_raw_value(source, name)
    if raw_value is None:
        return default

    try:
        parsed_value = float(raw_value)
    except ValueError as exc:
        raise ExecutionWorkerConfigError(
            f"{name} 必须是大于 0 的数字，当前值为 {raw_value}"
        ) from exc

    if parsed_value <= 0:
        raise ExecutionWorkerConfigError(
            f"{name} 必须大于 0，当前值为 {raw_value}"
        )
    return parsed_value
