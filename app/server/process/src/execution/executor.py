"""process 模块内的通用 HTTP 执行器。

第一版所有业务动作统一交给这一个执行器处理，不为每个 action_code 编写单独的 Python
执行器类。业务动作之间的差别全部来自配置：HTTP 方法、相对路径、超时时间和成功状态码
规则。新增业务动作只需要维护数据库配置，不需要发布后端代码。

执行器只负责发出一次请求并根据 HTTP 状态码判断结果，不修改审批状态，也不访问数据库。
"""

from collections.abc import Callable
from dataclasses import dataclass

import httpx

from app.common.scope import CallbackTarget
from app.server.process.src.constants import (
    EXECUTION_STATUS_FAILED,
    EXECUTION_STATUS_SUCCEEDED,
    MAX_ERROR_MESSAGE_LENGTH,
    MAX_RESPONSE_BODY_BYTES,
)
from app.server.process.src.models.execution_model import BusinessExecutionRecord


@dataclass(frozen=True)
class ExecutionOutcome:
    """一次业务执行的结果，由后台 Worker 写入执行记录。"""

    status: str
    # 实际请求地址。取得租户基础地址后补齐，配置缺失时为空。
    request_url: str | None = None
    http_status_code: int | None = None
    response_body: str | None = None
    error_message: str | None = None

    @classmethod
    def succeeded(
        cls,
        request_url: str,
        http_status_code: int,
        response_body: str | None,
    ) -> "ExecutionOutcome":
        """HTTP 状态码符合成功规则。"""

        return cls(
            status=EXECUTION_STATUS_SUCCEEDED,
            request_url=request_url,
            http_status_code=http_status_code,
            response_body=response_body,
        )

    @classmethod
    def failed(
        cls,
        error_message: str,
        request_url: str | None = None,
        http_status_code: int | None = None,
        response_body: str | None = None,
    ) -> "ExecutionOutcome":
        """配置缺失、网络异常、超时或状态码不符合成功规则。"""

        return cls(
            status=EXECUTION_STATUS_FAILED,
            request_url=request_url,
            http_status_code=http_status_code,
            response_body=response_body,
            error_message=truncate_characters(error_message, MAX_ERROR_MESSAGE_LENGTH),
        )


def is_success_status(
    http_status_code: int,
    success_status_codes: list[int] | None,
) -> bool:
    """按业务动作配置判断本次调用是否成功。

    配置了状态码时只有命中才算成功；没有配置时全部 2xx 视为成功。第一版不解析响应
    JSON 中的业务码。
    """

    if success_status_codes:
        return http_status_code in success_status_codes
    return 200 <= http_status_code < 300


def truncate_characters(value: str | None, max_length: int) -> str | None:
    """按字符数截断文本，用于长度由字符数约束的列，例如 VARCHAR(1000)。"""

    if value is None:
        return None
    if len(value) <= max_length:
        return value
    return value[: max_length - 1] + "…"


def truncate_utf8_bytes(value: str | None, max_bytes: int) -> str | None:
    """按 UTF-8 字节数截断文本。

    中文等多字节字符编码后占用多个字节，按字符数截断无法真正限制落库体积，因此响应
    正文统一按字节数限制。截断不能切在多字节字符中间，否则会得到非法 UTF-8 编码，
    这里先按字节切片再交给解码器丢弃被切开的半个字符。
    """

    if value is None:
        return None

    encoded_value = value.encode("utf-8")
    if len(encoded_value) <= max_bytes:
        return value

    suffix = "…"
    keep_bytes = max_bytes - len(suffix.encode("utf-8"))
    truncated_value = encoded_value[:keep_bytes].decode("utf-8", errors="ignore")
    return truncated_value + suffix


class BusinessActionExecutor:
    """复用同一个 HTTP Client 发送业务执行请求。

    httpx 的同步 Client 自身线程安全，并且内部维护连接池，因此整个 Worker 只创建一个
    实例，在应用关闭时统一关闭，避免每个任务都重新建立连接。
    """

    def __init__(
        self,
        client: httpx.Client | None = None,
        client_factory: Callable[[], httpx.Client] | None = None,
    ):
        """初始化执行器，并保留重新启动 Worker 时重建 Client 的工厂。

        生产环境使用默认工厂。测试注入自定义 Client 后如果还需要验证重启，必须同时
        注入可以创建同类 Client 的工厂；否则在已关闭 Client 上重新启动时会明确报错，
        不会等到领取任务后才把业务执行错误地标记为 FAILED。
        """

        self._client_factory = client_factory
        if client is None:
            self._client_factory = client_factory or self._create_default_client
            self._client = self._client_factory()
        else:
            self._client = client

    @staticmethod
    def _create_default_client() -> httpx.Client:
        """创建生产环境使用的同步 HTTP Client。"""

        return httpx.Client(
            # 回调地址必须来自租户登记的基础地址，不跟随业务系统返回的跳转。
            follow_redirects=False,
        )

    def open(self) -> None:
        """确保执行器持有可用 Client，支持同一个 Worker 停止后重新启动。"""

        if not self._client.is_closed:
            return
        if self._client_factory is None:
            raise RuntimeError(
                "业务执行器的 HTTP Client 已关闭，且没有配置重新创建 Client 的工厂"
            )
        self._client = self._client_factory()

    def execute(
        self,
        record: BusinessExecutionRecord,
        target: CallbackTarget,
    ) -> ExecutionOutcome:
        """使用执行记录中的配置快照向业务系统发出一次请求。

        调用方必须保证请求体使用执行记录里固化的 request_payload_json，认证只使用租户
        配置的 Service Token 请求头。Token 只在构造请求头时存在于内存中，不写日志、
        不写执行记录，也不出现在任何返回信息里。
        """

        request_url = target.build_url(record.relative_path or "")
        timeout_seconds = self._resolve_timeout_seconds(record.timeout_ms)

        try:
            with self._client.stream(
                record.http_method or "",
                request_url,
                json=dict(record.request_payload_json or {}),
                headers=target.build_headers(),
                timeout=timeout_seconds,
                # 认证头只在本次请求内使用，不写入任何持久化结构。
            ) as response:
                response_body = self._read_response_body(response)
                http_status_code = response.status_code
        except httpx.TimeoutException:
            return ExecutionOutcome.failed(
                f"调用业务系统超时（{timeout_seconds:g} 秒）",
                request_url=request_url,
            )
        except httpx.TransportError as exc:
            # 传输层异常信息只包含地址和网络原因，不包含认证请求头。
            return ExecutionOutcome.failed(
                f"无法连接业务系统：{exc}",
                request_url=request_url,
            )
        except httpx.InvalidURL:
            return ExecutionOutcome.failed(
                "业务动作相对路径无效，无法组成请求地址",
                request_url=request_url,
            )
        except httpx.HTTPError as exc:
            return ExecutionOutcome.failed(
                f"调用业务系统失败：{exc}",
                request_url=request_url,
            )
        except Exception as exc:  # noqa: BLE001 - 执行器不能把异常抛回轮询循环
            # 兜底异常只记录类型，避免异常信息里带出请求头等敏感内容。
            return ExecutionOutcome.failed(
                f"调用业务系统时发生未预期错误：{type(exc).__name__}",
                request_url=request_url,
            )

        if is_success_status(http_status_code, record.success_status_codes_json):
            return ExecutionOutcome.succeeded(
                request_url,
                http_status_code,
                response_body,
            )

        return ExecutionOutcome.failed(
            f"业务系统返回状态码 {http_status_code}，不符合成功状态码规则",
            request_url=request_url,
            http_status_code=http_status_code,
            response_body=response_body,
        )

    def close(self) -> None:
        """关闭复用的 HTTP Client，应用停止时调用。"""

        if not self._client.is_closed:
            self._client.close()

    @staticmethod
    def _resolve_timeout_seconds(timeout_ms: int | None) -> float:
        """把毫秒超时换算成秒，配置缺失时使用执行器兜底值。"""

        if not timeout_ms or timeout_ms <= 0:
            return 5.0
        return timeout_ms / 1000

    @staticmethod
    def _read_response_body(response: httpx.Response) -> str | None:
        """流式读取响应正文并在达到上限时提前停止。

        业务系统可能返回很大的正文，这里只读取截断上限以内的内容，避免为了保存几 KB
        结果而把一个巨大的响应完整读进内存。响应正文按 HTTP 响应的实际编码解码，
        不包含任何请求头信息。
        """

        collected_chunks: list[str] = []
        collected_bytes = 0
        try:
            for chunk in response.iter_text():
                collected_chunks.append(chunk)
                # 中文字符编码后占多个字节，按字节累计才能对上真实落库体积。
                collected_bytes += len(chunk.encode("utf-8"))
                if collected_bytes >= MAX_RESPONSE_BODY_BYTES:
                    break
        except httpx.HTTPError as exc:
            # 已经拿到状态码但正文读取失败，仍然保留状态码，正文按读取失败处理。
            return truncate_characters(
                f"响应正文读取失败：{type(exc).__name__}",
                MAX_ERROR_MESSAGE_LENGTH,
            )

        return truncate_utf8_bytes(
            "".join(collected_chunks),
            MAX_RESPONSE_BODY_BYTES,
        )
