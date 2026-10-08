"""文件批量上传、归属和审批附件关联的本地数据库测试。"""

import io
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import UploadFile
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from app.common.db.postgres_db import get_postgres_engine
from app.main import create_app
from app.server.file.src.models import ApprovalAttachment, FileRecord
from app.server.file.src.service import FileService, FileValidationError
from app.server.file.src.storage import LocalFileStorage, S3FileStorage


class FileServiceTestCase(unittest.TestCase):
    """验证批量上传要么全部成功，要么不产生可引用文件。"""

    def setUp(self) -> None:
        """创建独立目录和支持多 Schema 的 SQLite 测试数据库。"""

        self.directory = tempfile.TemporaryDirectory(prefix="approval-file-test-")
        self.storage = LocalFileStorage(Path(self.directory.name))
        self.service = FileService(self.storage)
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            execution_options={"schema_translate_map": {"file": None}},
        )
        # 只创建文件模块的表，避免测试依赖远程 PostgreSQL 和其他模块数据。
        FileRecord.__table__.create(self.engine)
        ApprovalAttachment.__table__.create(self.engine)
        self.db = Session(self.engine)

    def tearDown(self) -> None:
        """关闭数据库并清理测试产生的文件目录。"""

        self.db.close()
        self.engine.dispose()
        self.directory.cleanup()

    @staticmethod
    def upload(name: str, content: bytes) -> UploadFile:
        """创建与真实 multipart 上传等价的文件对象。"""

        return UploadFile(file=io.BytesIO(content), filename=name)

    def test_upload_batch_and_bind_in_order(self) -> None:
        """一批文件返回有序 ID，并可按同一顺序关联审批实例。"""

        tenant_id = uuid4()
        files = [
            self.upload("合同.pdf", b"%PDF-1.7\ncontract"),
            self.upload("凭证.png", b"\x89PNG\r\n\x1a\nimage"),
        ]
        records = self.service.upload_many(files, tenant_id, self.db)
        self.assertEqual([record.file_name for record in records], ["合同.pdf", "凭证.png"])
        self.assertEqual(len(self.db.exec(select(FileRecord)).all()), 2)

        validated = self.service.validate_references([record.id for record in records], tenant_id, self.db)
        instance_id = uuid4()
        self.service.bind_to_instance(instance_id, validated, self.db)
        self.db.commit()
        self.assertEqual(
            [record.id for record in self.service.list_for_instance(instance_id, self.db)],
            [record.id for record in records],
        )

    def test_invalid_file_rejects_entire_batch(self) -> None:
        """第二个文件非法时，第一个文件也不能留下元数据或对象。"""

        files = [
            self.upload("合同.pdf", b"%PDF-1.7\ncontract"),
            self.upload("伪造.pdf", b"not a PDF"),
        ]
        with self.assertRaisesRegex(FileValidationError, "files\\[1\\]"):
            self.service.upload_many(files, None, self.db)
        self.assertEqual(self.db.exec(select(FileRecord)).all(), [])
        self.assertEqual(list(Path(self.directory.name).rglob("*")), [])

    def test_missing_or_foreign_file_rejects_reference(self) -> None:
        """不存在的 ID 和其他租户的文件都不能附到审批单。"""

        tenant_id = uuid4()
        record = self.service.upload_many(
            [self.upload("材料.pdf", b"%PDF-1.7\ncontent")], tenant_id, self.db
        )[0]
        with self.assertRaisesRegex(FileValidationError, "file_id 不存在"):
            self.service.validate_references([uuid4()], tenant_id, self.db)
        with self.assertRaisesRegex(FileValidationError, "无权使用"):
            self.service.validate_references([record.id], uuid4(), self.db)
        with self.assertRaisesRegex(FileValidationError, "重复"):
            self.service.validate_references([record.id, record.id], tenant_id, self.db)

    def test_storage_failure_cleans_previous_objects(self) -> None:
        """第二个对象写入失败时清理已写对象，也不保存任何文件 ID。"""

        class FailingStorage(LocalFileStorage):
            """模拟第二次写入前存储故障的本地驱动。"""

            def __init__(self, root: Path):
                """记录写入次数以在第二个对象触发故障。"""

                super().__init__(root)
                self.put_count = 0

            def put(self, source: Path, object_key: str, content_type: str) -> None:
                """写入首个对象，并拒绝第二个对象。"""

                self.put_count += 1
                if self.put_count == 2:
                    raise OSError("模拟存储故障")
                super().put(source, object_key, content_type)

        failing_service = FileService(FailingStorage(Path(self.directory.name)))
        files = [
            self.upload("合同.pdf", b"%PDF-1.7\ncontract"),
            self.upload("凭证.png", b"\x89PNG\r\n\x1a\nimage"),
        ]
        with self.assertRaises(OSError):
            failing_service.upload_many(files, None, self.db)
        self.assertEqual(self.db.exec(select(FileRecord)).all(), [])
        self.assertEqual(
            [path for path in Path(self.directory.name).rglob("*") if path.is_file()],
            [],
        )


class FileApiTestCase(unittest.TestCase):
    """通过真实 multipart 请求验证批量上传与文件下载接口。"""

    def setUp(self) -> None:
        """使用独立 SQLite 和临时本地存储，关闭测试中的租户认证。"""

        self.directory = tempfile.TemporaryDirectory(prefix="approval-file-api-")
        self.previous_tenancy = os.environ.get("TENANCY_ENABLED")
        self.previous_storage_root = os.environ.get("APPROVAL_FILE_LOCAL_ROOT")
        self.previous_admin_key = os.environ.get("APPROVAL_ADMIN_KEY")
        os.environ["TENANCY_ENABLED"] = "false"
        os.environ["APPROVAL_FILE_LOCAL_ROOT"] = self.directory.name
        os.environ["APPROVAL_ADMIN_KEY"] = "test-admin-key"
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            execution_options={"schema_translate_map": {"file": None}},
        )
        FileRecord.__table__.create(self.engine)
        ApprovalAttachment.__table__.create(self.engine)
        app = create_app()

        def override_database_session():
            """为接口请求提供共享内存数据库会话。"""

            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_postgres_engine] = override_database_session
        self.client = TestClient(app)

    def tearDown(self) -> None:
        """释放请求资源并恢复测试前的环境变量。"""

        self.client.close()
        self.engine.dispose()
        self.directory.cleanup()
        self._restore_environment("TENANCY_ENABLED", self.previous_tenancy)
        self._restore_environment("APPROVAL_FILE_LOCAL_ROOT", self.previous_storage_root)
        self._restore_environment("APPROVAL_ADMIN_KEY", self.previous_admin_key)

    @staticmethod
    def _restore_environment(name: str, previous: str | None) -> None:
        """恢复单个环境变量，避免本测试影响其他接口用例。"""

        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous

    def test_batch_upload_and_download(self) -> None:
        """重复 files 字段上传两份文件后可通过返回的 ID 下载。"""

        response = self.client.post(
            "/api/files",
            files=[
                ("files", ("合同.pdf", b"%PDF-1.7\ncontract", "application/pdf")),
                ("files", ("凭证.png", b"\x89PNG\r\n\x1a\nimage", "image/png")),
            ],
        )
        self.assertEqual(response.status_code, 201, response.text)
        data = response.json()["data"]
        self.assertEqual(len(data["file_ids"]), 2)
        self.assertEqual([item["file_name"] for item in data["files"]], ["合同.pdf", "凭证.png"])

        download = self.client.get(
            f"/api/admin/files/{data['file_ids'][0]}/content",
            headers={"X-Admin-Key": "test-admin-key"},
        )
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, b"%PDF-1.7\ncontract")

    def test_invalid_second_file_returns_no_ids(self) -> None:
        """第二个文件无效时 HTTP 请求失败，数据库和对象存储均无残留。"""

        response = self.client.post(
            "/api/files",
            files=[
                ("files", ("合同.pdf", b"%PDF-1.7\ncontract", "application/pdf")),
                ("files", ("伪造.pdf", b"invalid", "application/pdf")),
            ],
        )
        self.assertEqual(response.status_code, 422)
        with Session(self.engine) as db:
            self.assertEqual(db.exec(select(FileRecord)).all(), [])
        self.assertEqual(list(Path(self.directory.name).rglob("*")), [])


class S3StorageConfigTestCase(unittest.TestCase):
    """不连接公网即可验证阿里云客户端的兼容配置。"""

    def test_aliyun_uses_v2_signature_and_virtual_host(self) -> None:
        """阿里云模式必须设置 boto3 的 S3 V2 签名和虚拟主机地址。"""

        class FakeConfig:
            """记录传给 botocore Config 的配置参数。"""

            def __init__(self, **options):
                """保存配置参数供断言检查。"""

                self.options = options

        boto3_module = types.ModuleType("boto3")
        boto3_module.client = Mock(return_value=object())
        botocore_module = types.ModuleType("botocore")
        config_module = types.ModuleType("botocore.config")
        config_module.Config = FakeConfig
        environment = {
            "APPROVAL_FILE_S3_PROVIDER": "aliyun",
            "APPROVAL_FILE_S3_BUCKET": "approval-files-demo",
            "APPROVAL_FILE_S3_REGION": "cn-hangzhou",
            "APPROVAL_FILE_S3_ENDPOINT": "https://s3.oss-cn-hangzhou.aliyuncs.com",
        }
        modules = {
            "boto3": boto3_module,
            "botocore": botocore_module,
            "botocore.config": config_module,
        }
        with patch.dict(sys.modules, modules), patch.dict(os.environ, environment):
            storage = S3FileStorage()

        self.assertEqual(storage.bucket, "approval-files-demo")
        _, options = boto3_module.client.call_args
        self.assertEqual(options["region_name"], "cn-hangzhou")
        self.assertEqual(options["config"].options["signature_version"], "s3")
        self.assertEqual(options["config"].options["s3"], {"addressing_style": "virtual"})
