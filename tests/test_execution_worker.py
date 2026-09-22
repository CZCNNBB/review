"""业务执行 Worker 测试。

SQLite 部分覆盖轮询、结果保存、并发上限和关闭行为；真实 PostgreSQL 部分验证
FOR UPDATE SKIP LOCKED 让一个任务只会被一个 Worker 领取。
"""

import os
import shutil
import tempfile
import threading
import time
import unittest
from uuid import UUID, uuid4

import httpx
from sqlmodel import Session, SQLModel, create_engine, select

from app.common.db.postgres_db import engine
from app.common.scope import (
    CallbackTargetResolver,
    CallbackTargetUnavailableError,
    CallbackTarget,
)
from app.server.integration.src.schemas.business_action_schema import (
    BusinessActionCreateRequest,
)
from app.server.integration.src.service.business_action_service import (
    BusinessActionService,
)
from app.server.process.src.constants import (
    EXECUTION_STATUS_FAILED,
    EXECUTION_STATUS_PENDING,
    EXECUTION_STATUS_RUNNING,
    EXECUTION_STATUS_SUCCEEDED,
)
from app.server.process.src.execution.executor import BusinessActionExecutor
from app.server.process.src.execution.settings import ExecutionWorkerSettings
from app.server.process.src.execution.worker import BusinessExecutionWorker
from app.server.process.src.models.approval_model import ApprovalInstance
from app.server.process.src.models.execution_model import BusinessExecutionRecord
from app.server.process.src.schemas.approval_schema import ApprovalStartRequest
from app.server.process.src.schemas.process_schema import (
    ProcessCreateRequest,
    ProcessGraphNodeRequest,
    ProcessGraphSaveRequest,
)
from app.server.process.src.service.approval_instance_service import (
    ApprovalInstanceService,
)
from app.server.process.src.service.process_service import ProcessService
from tests.process_test_helpers import (
    DatabaseTestCaseMixin,
    load_seed_node_definitions,
)


SERVICE_TOKEN = "service_token_worker_secret"


class StubCallbackTargetResolver(CallbackTargetResolver):
    """测试用的回调配置实现，返回固定目标或指定失败原因。"""

    def __init__(self, failure_message: str | None = None):
        """记录是否要模拟配置缺失。"""

        self.failure_message = failure_message

    def resolve(self, approval_instance_id: UUID, db: Session) -> CallbackTarget:
        """返回固定回调目标，或按配置抛出配置缺失。"""

        if self.failure_message:
            raise CallbackTargetUnavailableError(self.failure_message)
        return CallbackTarget(
            tenant_id=uuid4(),
            base_url="https://finance.example.com",
            header_name="Authorization",
            token_prefix="Bearer",
            token=SERVICE_TOKEN,
        )


class WorkerTestCase(unittest.TestCase):
    """验证 Worker 的领取、执行和结果保存。"""

    def setUp(self) -> None:
        """创建测试数据库并准备共享的 MockTransport 客户端。

        使用基于文件的 SQLite 而不是内存库：Worker 的并发执行会让多个线程各自持有
        独立会话，内存库的 StaticPool 只有一个共享连接，多线程同时提交会互相干扰。
        """

        self.temp_directory = tempfile.mkdtemp(prefix="business-execution-worker-")
        self.database_path = os.path.join(self.temp_directory, "worker-test.db")
        self.engine = create_engine(
            f"sqlite:///{self.database_path}",
            connect_args={
                "check_same_thread": False,
                # 多线程写入时等待文件锁，避免出现 database is locked。
                "timeout": 30,
            },
            execution_options={
                "schema_translate_map": {
                    "tenant": None,
                    "organization": None,
                    "process": None,
                    "integration": None,
                }
            },
        )
        SQLModel.metadata.create_all(self.engine)
        self.handled_requests: list[httpx.Request] = []
        self.handler = lambda request: httpx.Response(200, json={"ok": True})
        self.client = httpx.Client(
            transport=httpx.MockTransport(self.dispatch_request)
        )
        self.addCleanup(self.client.close)
        self.workers: list[BusinessExecutionWorker] = []

    def tearDown(self) -> None:
        """停止全部 Worker 并清理测试数据库文件。"""

        for worker in self.workers:
            worker.stop(timeout_seconds=10)
        self.engine.dispose()
        shutil.rmtree(self.temp_directory, ignore_errors=True)

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def dispatch_request(self, request: httpx.Request) -> httpx.Response:
        """记录请求并交给当前测试设置的处理器。"""

        self.handled_requests.append(request)
        return self.handler(request)

    def open_session(self) -> Session:
        """创建测试使用的数据库会话。"""

        return Session(self.engine, expire_on_commit=False)

    def build_worker(
        self,
        resolver: CallbackTargetResolver | None = None,
        batch_size: int = 10,
        concurrency: int = 5,
        poll_interval_seconds: float = 30.0,
        start: bool = False,
    ) -> BusinessExecutionWorker:
        """构造业务执行 Worker。"""

        worker = BusinessExecutionWorker(
            settings=ExecutionWorkerSettings(
                enabled=True,
                poll_interval_seconds=poll_interval_seconds,
                batch_size=batch_size,
                concurrency=concurrency,
            ),
            session_factory=self.open_session,
            callback_target_resolver=resolver or StubCallbackTargetResolver(),
            executor=BusinessActionExecutor(client=self.client),
        )
        self.workers.append(worker)
        if start:
            worker.start()
        return worker

    def create_record(
        self,
        http_method: str | None = "POST",
        relative_path: str | None = "/payment/execute",
        success_status_codes: list[int] | None = None,
        timeout_ms: int | None = 5000,
        status: str = EXECUTION_STATUS_PENDING,
    ) -> UUID:
        """创建一条执行记录并返回主键。"""

        with self.open_session() as db:
            record = BusinessExecutionRecord(
                approval_instance_id=uuid4(),
                action_code="PAYMENT_EXECUTE",
                http_method=http_method,
                relative_path=relative_path,
                success_status_codes_json=success_status_codes,
                timeout_ms=timeout_ms,
                request_payload_json={"payment_id": "PAY-001"},
                status=status,
            )
            db.add(record)
            db.commit()
            return record.id

    def get_record(self, record_id: UUID) -> BusinessExecutionRecord:
        """读取执行记录当前状态。"""

        with self.open_session() as db:
            return db.get(BusinessExecutionRecord, record_id)

    def list_records(self) -> list[BusinessExecutionRecord]:
        """读取全部执行记录。"""

        with self.open_session() as db:
            return list(db.exec(select(BusinessExecutionRecord)).all())

    # ------------------------------------------------------------------
    # 正常执行
    # ------------------------------------------------------------------

    def test_pending_record_is_executed_and_saved(self) -> None:
        """Worker 领取 PENDING 记录，调用业务系统后保存成功结果。"""

        record_id = self.create_record()
        worker = self.build_worker()

        processed = worker.run_once()

        self.assertEqual(processed, 1)
        record = self.get_record(record_id)
        self.assertEqual(record.status, EXECUTION_STATUS_SUCCEEDED)
        self.assertEqual(record.http_status_code, 200)
        self.assertEqual(record.request_url, "https://finance.example.com/payment/execute")
        self.assertIsNotNone(record.started_at)
        self.assertIsNotNone(record.finished_at)
        self.assertGreaterEqual(
            (record.finished_at - record.started_at).total_seconds(),
            0,
        )
        # 请求体来自记录里的参数快照。
        self.assertEqual(len(self.handled_requests), 1)

    def test_no_pending_record_does_nothing(self) -> None:
        """没有待执行记录时本轮不处理任何任务。"""

        worker = self.build_worker()

        self.assertEqual(worker.run_once(), 0)
        self.assertEqual(self.handled_requests, [])

    def test_terminal_records_are_not_claimed_again(self) -> None:
        """只有 PENDING 记录会被领取，已经结束的记录不会重复调用。"""

        self.create_record(status=EXECUTION_STATUS_SUCCEEDED)
        self.create_record(status=EXECUTION_STATUS_FAILED)
        worker = self.build_worker()

        self.assertEqual(worker.run_once(), 0)
        self.assertEqual(self.handled_requests, [])

    def test_batch_size_limits_claimed_records(self) -> None:
        """单批领取数量由配置决定。"""

        for _ in range(4):
            self.create_record()
        worker = self.build_worker(batch_size=2, concurrency=2)

        self.assertEqual(worker.run_once(), 2)
        self.assertEqual(len(self.handled_requests), 2)
        pending_records = [
            record
            for record in self.list_records()
            if record.status == EXECUTION_STATUS_PENDING
        ]
        self.assertEqual(len(pending_records), 2)

    def test_concurrency_limit_is_respected(self) -> None:
        """单进程内同时执行的请求数量不超过并发配置。"""

        active_requests = 0
        max_active_requests = 0
        lock = threading.Lock()

        def slow_handler(request: httpx.Request) -> httpx.Response:
            nonlocal active_requests, max_active_requests
            with lock:
                active_requests += 1
                max_active_requests = max(max_active_requests, active_requests)
            time.sleep(0.05)
            with lock:
                active_requests -= 1
            return httpx.Response(200)

        self.handler = slow_handler
        for _ in range(6):
            self.create_record()
        worker = self.build_worker(batch_size=6, concurrency=2)

        worker.run_once()

        self.assertEqual(max_active_requests, 2)
        statuses = {record.status for record in self.list_records()}
        self.assertEqual(statuses, {EXECUTION_STATUS_SUCCEEDED})

    # ------------------------------------------------------------------
    # 失败结果
    # ------------------------------------------------------------------

    def test_missing_action_snapshot_fails_without_http_call(self) -> None:
        """业务动作快照缺失时直接判失败，不发出请求，也不解析租户。"""

        record_id = self.create_record(http_method=None, relative_path=None)
        worker = self.build_worker()

        worker.run_once()

        record = self.get_record(record_id)
        self.assertEqual(record.status, EXECUTION_STATUS_FAILED)
        self.assertIn("业务动作配置缺失", record.error_message)
        self.assertIsNone(record.http_status_code)
        self.assertEqual(self.handled_requests, [])

    def test_missing_tenant_config_fails_with_reason(self) -> None:
        """租户回调配置不可用时记录明确失败原因，不发出请求。"""

        record_id = self.create_record()
        worker = self.build_worker(
            resolver=StubCallbackTargetResolver("租户没有可用的 Service Token 凭据")
        )

        worker.run_once()

        record = self.get_record(record_id)
        self.assertEqual(record.status, EXECUTION_STATUS_FAILED)
        self.assertEqual(record.error_message, "租户没有可用的 Service Token 凭据")
        self.assertEqual(self.handled_requests, [])

    def test_service_token_never_reaches_the_record(self) -> None:
        """执行记录里不能出现 Service Token。"""

        def failing_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        self.handler = failing_handler
        record_id = self.create_record()
        worker = self.build_worker()

        worker.run_once()

        record = self.get_record(record_id)
        self.assertEqual(record.status, EXECUTION_STATUS_FAILED)
        self.assertNotIn(SERVICE_TOKEN, record.error_message or "")
        self.assertNotIn(SERVICE_TOKEN, record.response_body or "")
        self.assertNotIn(SERVICE_TOKEN, record.request_url or "")

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def test_stopped_worker_leaves_pending_records_untouched(self) -> None:
        """关闭后不再领取任务，停止期间写入的记录只留下 PENDING。

        启动时队列为空，Worker 进入轮询等待；此时写入一条记录并立即关闭，记录不会被
        领取，留给下次启动继续处理。
        """

        worker = self.build_worker(poll_interval_seconds=30.0, start=True)
        record_id = self.create_record()
        worker.stop(timeout_seconds=10)

        self.assertEqual(self.handled_requests, [])
        record = self.get_record(record_id)
        self.assertEqual(record.status, EXECUTION_STATUS_PENDING)
        self.assertIsNone(record.started_at)
        self.assertIsNone(record.finished_at)

    def test_started_worker_drains_claimed_batch_before_stopping(self) -> None:
        """关闭时等待当前批次结束，不把记录留在 RUNNING。"""

        processed = threading.Event()

        def handler(request: httpx.Request) -> httpx.Response:
            time.sleep(0.2)
            processed.set()
            return httpx.Response(200)

        self.handler = handler
        self.create_record()
        worker = self.build_worker(
            batch_size=1,
            concurrency=1,
            poll_interval_seconds=0.01,
            start=True,
        )

        self.assertTrue(processed.wait(timeout=10))
        worker.stop(timeout_seconds=10)

        statuses = {record.status for record in self.list_records()}
        self.assertEqual(statuses, {EXECUTION_STATUS_SUCCEEDED})

    def test_start_is_idempotent_and_worker_can_restart(self) -> None:
        """重复启动不会创建第二个循环，停止后可以重新启动。"""

        worker = self.build_worker(poll_interval_seconds=30.0, start=True)
        worker.start()
        worker.stop(timeout_seconds=10)
        worker.start()
        worker.stop(timeout_seconds=10)

        self.assertEqual(self.handled_requests, [])


class WorkerSkipLockedTestCase(DatabaseTestCaseMixin, unittest.TestCase):
    """验证多个 Worker 并发领取时 PostgreSQL 不会把同一任务发给两个进程。"""

    def setUp(self) -> None:
        """准备真实数据库会话、流程和业务动作。"""

        self.db: Session = self.open_session()
        self.process_service = ProcessService()
        self.instance_service = ApprovalInstanceService()
        self.seed = load_seed_node_definitions()
        self.record_ids: list[UUID] = []
        self.handled_requests: list[httpx.Request] = []
        self.workers: list[BusinessExecutionWorker] = []
        self._handled_lock = threading.Lock()
        self._create_action()

    def tearDown(self) -> None:
        """停止 Worker 并清理流程数据。"""

        for worker in self.workers:
            worker.stop(timeout_seconds=10)
        self.close_session()

    def _create_action(self) -> None:
        """创建执行记录里用到的业务动作配置。"""

        action = BusinessActionService().create_action(
            BusinessActionCreateRequest(
                action_code="PAYMENT_EXECUTE",
                name="执行并发测试动作",
                http_method="POST",
                relative_path="/payment/execute",
            ),
            self.db,
        )
        self.track_business_action(action.id)

    def publish_start_to_end_process(self) -> UUID:
        """发布 开始 → 结束(通过) 的最小流程并返回流程 ID。"""

        overview = self.process_service.create_process(
            ProcessCreateRequest(
                name=f"执行并发测试流程-{uuid4().hex[:8]}",
                form_schema={"type": "object", "properties": {}},
            ),
            self.db,
        )
        self.track_process(overview.process.id)

        start_node = ProcessGraphNodeRequest(
            id=uuid4(),
            node_definition_id=self.seed["START"].id,
            name="开始",
            config={},
            position={"x": 100, "y": 100},
        )
        end_node = ProcessGraphNodeRequest(
            id=uuid4(),
            node_definition_id=self.seed["END"].id,
            name="结束",
            config={"result_status": "APPROVED"},
            position={"x": 300, "y": 100},
        )
        draft_version = self.process_service.repository.get_draft_version(
            overview.process.id,
            self.db,
        )
        self.process_service.save_graph(
            draft_version.id,
            ProcessGraphSaveRequest(
                revision=draft_version.revision,
                name=draft_version.name,
                form_schema={"type": "object", "properties": {}},
                nodes=[start_node, end_node],
                orchestration={
                    "connections": [
                        {
                            "source_node_id": str(start_node.id),
                            "target_node_id": str(end_node.id),
                        }
                    ]
                },
            ),
            self.db,
        )
        self.process_service.publish_version(draft_version.id, self.db)
        return overview.process.id

    def create_pending_records(self, process_id: UUID, count: int) -> list[UUID]:
        """通过真实审批实例创建待执行记录。

        开始 → 结束(通过) 的实例在发起事务里就直接结束并创建 PENDING 执行记录，
        因此这里同时验证了这条路径确实挂在了统一结束入口上。
        """

        record_ids: list[UUID] = []
        for _ in range(count):
            started = self.instance_service.start_instance(
                process_id,
                ApprovalStartRequest(
                    business_key=f"BIZ-{uuid4().hex[:8]}",
                    title="直接结束的申请",
                    action_code="PAYMENT_EXECUTE",
                    approval_form={},
                    execution_payload={"payment_id": "PAY-001"},
                ),
                self.db,
            )
            instance = self.db.get(ApprovalInstance, started.instance.id)
            self.assertEqual(instance.status, "APPROVED")

            record = self.db.exec(
                select(BusinessExecutionRecord).where(
                    BusinessExecutionRecord.approval_instance_id == instance.id
                )
            ).first()
            self.assertIsNotNone(record)
            self.assertEqual(record.status, EXECUTION_STATUS_PENDING)
            record_ids.append(record.id)

        self.record_ids = record_ids
        return record_ids

    def build_worker(self, size: int) -> BusinessExecutionWorker:
        """构造使用真实数据库会话的 Worker。"""

        def handler(request: httpx.Request) -> httpx.Response:
            with self._handled_lock:
                self.handled_requests.append(request)
            return httpx.Response(200)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(client.close)

        worker = BusinessExecutionWorker(
            settings=ExecutionWorkerSettings(
                enabled=True,
                poll_interval_seconds=30.0,
                batch_size=size,
                concurrency=size,
            ),
            session_factory=lambda: Session(engine, expire_on_commit=False),
            callback_target_resolver=StubCallbackTargetResolver(),
            executor=BusinessActionExecutor(client=client),
        )
        self.workers.append(worker)
        return worker

    def test_two_workers_never_claim_the_same_record(self) -> None:
        """并发领取时一条记录只会被一个 Worker 拿到。"""

        process_id = self.publish_start_to_end_process()
        record_ids = self.create_pending_records(process_id, 6)
        batch_size = len(record_ids)

        first_worker = self.build_worker(batch_size)
        second_worker = self.build_worker(batch_size)

        barrier = threading.Barrier(2)
        errors: list[Exception] = []

        def run(worker: BusinessExecutionWorker) -> None:
            try:
                # 两个 Worker 在同一个瞬间竞争同一批 PENDING 记录。
                barrier.wait(timeout=10)
                worker.run_once()
            except Exception as exc:  # noqa: BLE001 - 测试需要把异常带回主线程
                errors.append(exc)

        threads = [
            threading.Thread(target=run, args=(first_worker,)),
            threading.Thread(target=run, args=(second_worker,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        self.assertEqual(errors, [])
        # 没有 SKIP LOCKED 时两个 Worker 会各自领走全部记录，请求数量会翻倍。
        self.assertEqual(len(self.handled_requests), len(record_ids))

        self.db.expire_all()
        records = [
            self.db.get(BusinessExecutionRecord, record_id)
            for record_id in record_ids
        ]
        for record in records:
            self.assertEqual(record.status, EXECUTION_STATUS_SUCCEEDED)
            self.assertEqual(record.http_status_code, 200)


if __name__ == "__main__":
    unittest.main()
