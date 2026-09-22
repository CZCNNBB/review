"""后台业务执行 Worker：轮询待执行记录并调用业务系统接口。

Worker 在独立线程中运行，不占用 FastAPI 的事件循环。整个后端使用同步的 SQLModel
Session（psycopg2），如果直接在 asyncio 协程里查询数据库，会阻塞事件循环并让整个 API
服务停摆，因此这里统一使用后台线程加线程池。

每次领取、每次结果保存都使用独立 Session；HTTP 请求期间不持有任何数据库会话和行锁。
"""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager
from uuid import UUID

import httpx
from sqlmodel import Session

from app.common.db.postgres_db import engine
from app.common.scope import (
    CallbackTargetUnavailableError,
    CallbackTarget,
    CallbackTargetResolver,
)
from app.server.process.src.constants import EXECUTION_ERROR_ACTION_MISSING
from app.server.process.src.execution.executor import (
    BusinessActionExecutor,
    ExecutionOutcome,
)
from app.server.process.src.execution.settings import ExecutionWorkerSettings
from app.server.process.src.models.execution_model import BusinessExecutionRecord
from app.server.process.src.models.process_model import utc_now
from app.server.process.src.repository.execution_repository import (
    BusinessExecutionRepository,
)
from app.server.tenant.src.scope.callback_config import (
    create_callback_target_resolver,
)

logger = logging.getLogger(__name__)


def _default_session_factory() -> Session:
    """创建 Worker 使用的独立数据库会话。

    关闭 commit 后过期：领取事务提交后仍然需要读取刚才标记为 RUNNING 的记录，如果
    提交就让对象过期，读取属性会重新发起查询并使用已经关闭的会话。
    """

    return Session(engine, expire_on_commit=False)


class BusinessExecutionWorker:
    """轮询 PENDING 记录并在后台线程池中执行单次 HTTP 调用。"""

    def __init__(
        self,
        settings: ExecutionWorkerSettings,
        session_factory: Callable[[], AbstractContextManager[Session]] | None = None,
        callback_target_resolver: CallbackTargetResolver | None = None,
        executor: BusinessActionExecutor | None = None,
        repository: BusinessExecutionRepository | None = None,
        http_client: httpx.Client | None = None,
    ):
        """初始化 Worker 并允许测试注入依赖。"""

        self.settings = settings
        # process 只依赖 app.common.scope 定义的端口，默认实现由 tenant 模块在应用层装配。
        self.callback_target_resolver = (
            callback_target_resolver or create_callback_target_resolver()
        )
        self.repository = repository or BusinessExecutionRepository()
        self._session_factory = session_factory or _default_session_factory
        self.executor = executor or BusinessActionExecutor(client=http_client)
        self._pool: ThreadPoolExecutor | None = None
        # 领取锁让“提交 RUNNING”和“发出停止信号”之间有明确边界，避免停机开始后
        # 协调线程又领取一批新任务。
        self._claim_lock = threading.Lock()
        # 守护线程只用于应对进程被强制终止的最后兜底；正常关闭由 lifespan 等待完成。
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self) -> None:
        """启动后台轮询线程，重复调用不会创建第二个循环。"""

        if self._thread is not None and self._thread.is_alive():
            return

        # stop() 会关闭连接池；再次启动同一个 Worker 时必须先创建新的 HTTP Client，
        # 否则任务虽然能被领取，却会在发送请求时因 Client 已关闭而全部失败。
        self.executor.open()
        self._ensure_pool()
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="business-execution-worker",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout_seconds: float | None = None) -> bool:
        """通知轮询停止，等待当前批次结束后释放线程池和 HTTP Client。

        停止后不再领取新任务，仍然停留在 PENDING 的记录留给下次启动继续处理。
        默认不设置内部超时，确保已经领取为 RUNNING 的任务保存最终结果后才返回。测试或
        运维探测可以显式传入超时时间；返回 False 时不能关闭仍在使用的 Client，调用方
        可以稍后再次调用 stop() 完成资源回收。
        """

        # 等待正在进行的领取事务提交，再发出停止信号。锁释放之后，协调线程无法再开始
        # 新的领取事务；此时已经提交为 RUNNING 的记录属于必须完成的在途任务。
        with self._claim_lock:
            self._stop_event.set()

        thread = self._thread
        if thread is not None:
            thread.join(timeout_seconds)
            if thread.is_alive():
                # HTTP 请求还在执行时不能关闭共享 Client，也不能把线程引用清空，否则
                # 后续 start() 可能与旧线程并行运行并破坏执行状态。
                logger.warning(
                    "业务执行 Worker 在 %s 秒内没有停止，仍有请求在执行中",
                    timeout_seconds,
                )
                return False
        self._thread = None

        pool = self._pool
        if pool is not None:
            # 协调线程退出前会等待当前批次的 Future，因此这里可以安全关闭线程池，不会
            # 把已经标记 RUNNING 但尚未开始的任务取消在半路。
            pool.shutdown(wait=True, cancel_futures=False)
            self._pool = None
        self.executor.close()
        return True

    def _ensure_pool(self) -> ThreadPoolExecutor:
        """延迟创建线程池，支持 start 和 stop 反复调用。"""

        if self._pool is None:
            self._pool = ThreadPoolExecutor(
                max_workers=self.settings.concurrency,
                thread_name_prefix="business-execution",
            )
        return self._pool

    # ------------------------------------------------------------------
    # 轮询
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """按配置的间隔轮询待执行记录，直到收到停止通知。"""

        while not self._stop_event.is_set():
            try:
                processed = self.run_once()
            except Exception:  # noqa: BLE001 - 轮询循环不能因为单轮失败而退出
                logger.exception("业务执行 Worker 本轮轮询失败，将在下个周期重试")
                processed = 0

            if processed < self.settings.batch_size:
                # 本轮没有把批次领满，说明队列已经清空，等待下一个轮询周期。
                self._stop_event.wait(self.settings.poll_interval_seconds)

    def _claim_limit(self, remaining_batch_size: int) -> int:
        """返回当前一波能够立即交给线程池执行的最大任务数量。"""

        # 不领取超过并发槽位的任务，避免任务只是在执行器队列中等待，却已经被数据库
        # 标记为 RUNNING。这样关闭服务时只需等待真正开始处理的任务。
        return min(remaining_batch_size, self.settings.concurrency)

    def run_once(self) -> int:
        """领取并处理一批待执行记录，返回本批实际处理的记录数量。

        领取是独立短事务：锁定 PENDING 记录、标记 RUNNING 并提交，随后才在事务外发起
        HTTP 请求，避免拿着数据库行锁等待外部接口。
        """

        processed_count = 0
        pool = self._ensure_pool()

        # 一个轮询批次可以包含多波执行。每波最多领取并发数条，等本波完成后再领取
        # 下一波，因此数据库里的 RUNNING 数量始终对应真正占用执行槽位的任务。
        while (
            processed_count < self.settings.batch_size
            and not self._stop_event.is_set()
        ):
            remaining_batch_size = self.settings.batch_size - processed_count
            claim_limit = self._claim_limit(remaining_batch_size)
            claimed_records = self._claim_batch(claim_limit)
            if not claimed_records:
                break

            futures = [
                pool.submit(self._process_record, record) for record in claimed_records
            ]
            for future in futures:
                # _process_record 内部已经兜住全部异常，这里只做同步等待。
                future.result()
            processed_count += len(claimed_records)

        return processed_count

    def _claim_batch(self, claim_limit: int) -> list[BusinessExecutionRecord]:
        """在短事务中领取一批 PENDING 记录并标记为 RUNNING。"""

        with self._claim_lock:
            # stop() 已经发出信号后不再打开会话，也不再领取新任务。
            if self._stop_event.is_set():
                return []

            with self._session_factory() as db:
                try:
                    records = self.repository.claim_pending_records(
                        claim_limit,
                        db,
                    )
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
                return records

    # ------------------------------------------------------------------
    # 单条记录处理
    # ------------------------------------------------------------------

    def _process_record(self, record: BusinessExecutionRecord) -> None:
        """解析租户配置、发送一次请求并保存结果。"""

        try:
            outcome = self._execute_record(record)
        except Exception:  # noqa: BLE001 - 单条任务失败不能影响本批其他任务
            logger.exception(
                "业务执行记录 %s 处理失败，已保留为 RUNNING 等待人工核对",
                record.id,
            )
            return

        self._save_outcome(record.id, outcome)

    def _execute_record(self, record: BusinessExecutionRecord) -> ExecutionOutcome:
        """生成一次业务调用的结果。"""

        # 业务动作快照缺失时无需解析租户，直接给出可查询的失败原因。
        if not record.http_method or not record.relative_path:
            return ExecutionOutcome.failed(EXECUTION_ERROR_ACTION_MISSING)

        try:
            target = self._resolve_target(record.approval_instance_id)
        except CallbackTargetUnavailableError as exc:
            return ExecutionOutcome.failed(str(exc))

        return self.executor.execute(record, target)

    def _resolve_target(self, approval_instance_id: UUID) -> CallbackTarget:
        """用独立会话读取租户回调配置，读取完成后立即释放会话。

        审批事务提交前租户使用记录可能还没有写入，因此租户解析只能在事务提交之后由
        Worker 完成。
        """

        with self._session_factory() as db:
            return self.callback_target_resolver.resolve(approval_instance_id, db)

    def _save_outcome(self, record_id: UUID, outcome: ExecutionOutcome) -> None:
        """用独立会话保存执行结果，HTTP 请求已经结束，此时才重新占用数据库连接。"""

        with self._session_factory() as db:
            updated = self.repository.save_result(
                record_id=record_id,
                status=outcome.status,
                request_url=outcome.request_url,
                http_status_code=outcome.http_status_code,
                response_body=outcome.response_body,
                error_message=outcome.error_message,
                finished_at=utc_now(),
                db=db,
            )
            if not updated:
                # 记录不再是 RUNNING，说明状态已被其他来源改变。保留现状并留下可排查的日志。
                logger.warning(
                    "业务执行记录 %s 已不是 RUNNING，本次结果未写入",
                    record_id,
                )
