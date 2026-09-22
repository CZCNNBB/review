"""业务执行 Worker 的启动和停止。

由 FastAPI 的 lifespan 调用。启动阶段完成全部配置校验，配置不合法时直接让应用启动
失败，而不是带着错误的轮询参数运行到线上。
"""

import logging

from app.server.process.src.execution.settings import (
    ExecutionWorkerConfigError,
    ExecutionWorkerSettings,
)
from app.server.process.src.execution.worker import BusinessExecutionWorker
from app.server.tenant.src.utils.credential import CredentialCipher

logger = logging.getLogger(__name__)


class BusinessExecutionStartupError(Exception):
    """业务执行 Worker 无法按当前配置启动。"""


def start_business_execution_worker() -> BusinessExecutionWorker | None:
    """按环境变量启动业务执行 Worker，未启用时返回空。

    停用 Worker 时审批通过仍然正常创建 PENDING 记录，只是当前进程不领取任务，适用于
    只提供 API 的进程或后续部署独立 Worker 的场景。
    """

    try:
        settings = ExecutionWorkerSettings.from_environment()
    except ExecutionWorkerConfigError as exc:
        raise BusinessExecutionStartupError(str(exc)) from exc

    if not settings.enabled:
        logger.info("业务执行 Worker 未启用，审批通过后只创建 PENDING 执行记录")
        return None

    # Worker 必须能够解密 Service Token 才有意义。主密钥缺失或格式错误时直接启动失败，
    # 避免应用正常运行但每一条执行记录都在解密阶段失败。
    _ensure_credential_master_key()

    worker = BusinessExecutionWorker(settings)
    worker.start()
    logger.info(
        "业务执行 Worker 已启动：轮询间隔 %.1f 秒，单批 %d 条，单进程并发 %d",
        settings.poll_interval_seconds,
        settings.batch_size,
        settings.concurrency,
    )
    return worker


def stop_business_execution_worker(worker: BusinessExecutionWorker | None) -> None:
    """停止领取新任务，等待 RUNNING 任务结束并关闭 Worker 资源。"""

    if worker is None:
        return

    # 正常关闭不设置内部等待上限：已经领取为 RUNNING 的任务必须先保存最终结果，尚未领取
    # 的 PENDING 任务保留到服务下次启动后处理。
    worker.stop(timeout_seconds=None)
    logger.info("业务执行 Worker 已停止")


def _ensure_credential_master_key() -> None:
    """确认 Service Token 加密主密钥可用。"""

    try:
        CredentialCipher.from_environment()
    except ValueError as exc:
        raise BusinessExecutionStartupError(
            f"{exc}；启用业务执行 Worker 时必须配置可用的 Service Token 加密主密钥"
        ) from exc
