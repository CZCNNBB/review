"""抄送节点自动推进和只读收件记录的关键行为测试。"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.server.process.src.engine.nodes.copy import CopyNodeHandler
from app.server.process.src.engine.runner import ApprovalEngine
from app.server.process.src.schemas.approval_schema import ApprovalTaskActionRequest
from app.server.process.src.service.approval_task_service import ApprovalTaskService
from app.server.process.src.service.approval_workbench_service import ApprovalWorkbenchService
from app.server.process.src.service.exceptions import (
    ApprovalPermissionError,
    ApprovalStateError,
)


class CopyNodeTestCase(unittest.TestCase):
    """验证抄送不创建审批任务，也不阻断后续节点。"""

    def test_handler_records_recipients_and_continues(self) -> None:
        """节点进入后先写收件记录，再沿普通连线继续。"""

        recipient_id = uuid4()
        next_node_id = uuid4()
        engine = MagicMock()
        engine.resolve_copy_recipient_person_ids.return_value = [recipient_id]
        engine.complete_node.return_value = next_node_id
        execution = SimpleNamespace(result_json={})
        context = SimpleNamespace(
            engine=engine,
            instance=SimpleNamespace(id=uuid4()),
            graph=object(),
            execution=execution,
            node=SimpleNamespace(name="抄送", config_json={}),
            db=object(),
        )

        result = CopyNodeHandler().handle(context)

        self.assertEqual(result, next_node_id)
        self.assertEqual(execution.result_json["recipient_person_ids"], [str(recipient_id)])
        engine.create_copy_records.assert_called_once()
        engine.complete_node.assert_called_once()
        engine.create_approval_tasks.assert_not_called()

    def test_engine_creates_one_read_only_record_per_recipient(self) -> None:
        """抄送记录保存人员快照，并以 COPY 类型写入统一任务表。"""

        recipient_id = uuid4()
        repository = MagicMock()
        organization_service = MagicMock()
        engine = ApprovalEngine(
            repository=repository,
            organization_service=organization_service,
        )
        engine.load_person_snapshots = MagicMock(
            return_value={recipient_id: {"person_id": str(recipient_id), "name": "抄送人"}}
        )
        instance = SimpleNamespace(id=uuid4())
        execution = SimpleNamespace(id=uuid4())
        db = MagicMock()

        engine.create_copy_records(instance, execution, [recipient_id], db)

        copies = repository.add_copies.call_args.args[0]
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0].recipient_person_id, recipient_id)
        self.assertEqual(copies[0].recipient_snapshot_json["name"], "抄送人")
        self.assertEqual(copies[0].task_type, "COPY")
        self.assertEqual(copies[0].status, "RECEIVED")
        repository.add_tasks.assert_not_called()

    def test_copy_task_cannot_be_approved(self) -> None:
        """即便知道统一任务表中的抄送任务 ID，也不能调用同意接口处理。"""

        person_id = uuid4()
        task = SimpleNamespace(
            id=uuid4(),
            instance_id=uuid4(),
            task_type="COPY",
            recipient_person_id=person_id,
        )
        repository = MagicMock()
        repository.get_task_by_id.return_value = task
        repository.get_instance_for_update.return_value = SimpleNamespace(id=task.instance_id)
        repository.get_task_for_update.return_value = task
        service = ApprovalTaskService(repository=repository)

        with self.assertRaisesRegex(ApprovalStateError, "抄送任务仅供查看"):
            service.approve(
                task.id,
                ApprovalTaskActionRequest(person_id=person_id),
                MagicMock(),
            )

        repository.add_record.assert_not_called()

    def test_unified_task_detail_checks_recipient_for_copy(self) -> None:
        """统一详情入口可读取抄送审批单，并拒绝非收件人查看。"""

        recipient_id = uuid4()
        task = SimpleNamespace(
            id=uuid4(),
            instance_id=uuid4(),
            recipient_person_id=recipient_id,
            task_type="COPY",
        )
        repository = MagicMock()
        repository.get_task_by_id.return_value = task
        instance_service = MagicMock()
        expected_view = object()
        instance_service.get_instance_view.return_value = expected_view
        service = ApprovalWorkbenchService(
            repository=repository,
            instance_service=instance_service,
        )
        db = MagicMock()

        self.assertIs(
            service.get_recipient_instance_view(task.id, recipient_id, db),
            expected_view,
        )
        instance_service.get_instance_view.assert_called_once_with(task.instance_id, db)
        with self.assertRaises(ApprovalPermissionError):
            service.get_recipient_instance_view(task.id, uuid4(), db)
