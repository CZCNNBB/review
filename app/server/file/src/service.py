"""批量上传、文件归属校验和审批附件绑定服务。"""

import hashlib
import logging
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Sequence
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlmodel import Session, select

from app.server.file.src.models import ApprovalAttachment, FileRecord
from app.server.file.src.storage import FileStorage, create_storage


logger = logging.getLogger(__name__)
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_BATCH_BYTES = 100 * 1024 * 1024
MAX_FILES = 10
CHUNK_BYTES = 64 * 1024
CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class FileValidationError(Exception):
    """上传参数或文件引用不符合业务规则。"""


class FileAccessError(Exception):
    """文件不存在或当前租户无权读取。"""


@dataclass(frozen=True)
class StagedFile:
    """一个已完成大小、类型和摘要检查的临时文件。"""

    path: Path
    name: str
    content_type: str
    size_bytes: int
    sha256: str


class FileService:
    """管理文件本体、元数据和审批实例附件关联。"""

    def __init__(self, storage: FileStorage | None = None):
        """允许测试注入存储实现，正常运行时按配置创建。"""

        self.storage = storage or create_storage()

    @staticmethod
    def _validate_signature(name: str, first_bytes: bytes) -> str:
        """用扩展名和内容签名共同限制支持的文件类型。"""

        extension = Path(name).suffix.lower()
        content_type = CONTENT_TYPES.get(extension)
        if content_type is None:
            raise FileValidationError(f"文件 {name} 的类型不受支持")
        signatures = {
            ".pdf": (b"%PDF-",),
            ".png": (b"\x89PNG\r\n\x1a\n",),
            ".jpg": (b"\xff\xd8\xff",),
            ".jpeg": (b"\xff\xd8\xff",),
            ".docx": (b"PK\x03\x04",),
            ".xlsx": (b"PK\x03\x04",),
        }
        if not any(first_bytes.startswith(signature) for signature in signatures[extension]):
            raise FileValidationError(f"文件 {name} 的内容与扩展名不符")
        return content_type

    @staticmethod
    def _validate_office_package(name: str, path: Path) -> None:
        """检查 Office 压缩包的核心条目，避免普通 ZIP 冒充文档。"""

        extension = Path(name).suffix.lower()
        if extension not in {".docx", ".xlsx"}:
            return
        required_entry = "word/document.xml" if extension == ".docx" else "xl/workbook.xml"
        try:
            with zipfile.ZipFile(path) as archive:
                if required_entry not in archive.namelist():
                    raise FileValidationError(f"文件 {name} 的内容与扩展名不符")
        except zipfile.BadZipFile as exc:
            raise FileValidationError(f"文件 {name} 不是有效的 Office 文档") from exc

    @classmethod
    def _stage_file(cls, upload: UploadFile, directory: Path, index: int) -> StagedFile:
        """分块暂存一个文件并计算摘要，避免把整批内容读进内存。"""

        name = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
        if not name or len(name) > 255:
            raise FileValidationError(f"第 {index + 1} 个文件的名称无效")
        path = directory / f"{index}.upload"
        digest = hashlib.sha256()
        size = 0
        first_bytes = b""
        with path.open("wb") as target:
            while True:
                chunk = upload.file.read(CHUNK_BYTES)
                if not chunk:
                    break
                if not first_bytes:
                    first_bytes = chunk[:16]
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    raise FileValidationError(f"文件 {name} 超过 20 MiB 上限")
                digest.update(chunk)
                target.write(chunk)
        if size == 0:
            raise FileValidationError(f"文件 {name} 为空")
        content_type = cls._validate_signature(name, first_bytes)
        cls._validate_office_package(name, path)
        return StagedFile(path, name, content_type, size, digest.hexdigest())

    def upload_many(
        self,
        files: Sequence[UploadFile],
        tenant_id: UUID | None,
        db: Session,
    ) -> list[FileRecord]:
        """整批校验和保存文件；任一步失败都不返回部分 file_id。"""

        if not 1 <= len(files) <= MAX_FILES:
            raise FileValidationError(f"一次须上传 1 至 {MAX_FILES} 个文件")

        with tempfile.TemporaryDirectory(prefix="approval-upload-") as temp_directory:
            directory = Path(temp_directory)
            staged: list[StagedFile] = []
            total_bytes = 0
            for index, upload in enumerate(files):
                try:
                    item = self._stage_file(upload, directory, index)
                except FileValidationError as exc:
                    raise FileValidationError(f"files[{index}]：{exc}") from exc
                staged.append(item)
                total_bytes += item.size_bytes
                if total_bytes > MAX_BATCH_BYTES:
                    raise FileValidationError("整批文件超过 100 MiB 上限")

            batch_id = uuid4()
            records: list[FileRecord] = []
            stored_keys: list[str] = []
            try:
                for item in staged:
                    file_id = uuid4()
                    owner = str(tenant_id) if tenant_id is not None else "global"
                    object_key = f"{owner}/{batch_id}/{file_id}"
                    # 先登记待补偿键：存储驱动可能在写了一部分对象后才报错。
                    stored_keys.append(object_key)
                    self.storage.put(item.path, object_key, item.content_type)
                    records.append(
                        FileRecord(
                            id=file_id,
                            tenant_id=tenant_id,
                            object_key=object_key,
                            file_name=item.name,
                            content_type=item.content_type,
                            size_bytes=item.size_bytes,
                            sha256=item.sha256,
                        )
                    )
                db.add_all(records)
                db.commit()
                return records
            except Exception:
                db.rollback()
                # 对象存储与数据库不能共享事务；失败时补偿删除本批已上传对象。
                for object_key in stored_keys:
                    try:
                        self.storage.delete(object_key)
                    except Exception:
                        logger.exception("批量上传回滚时清理对象失败：%s", object_key)
                raise

    @staticmethod
    def validate_references(
        file_ids: Sequence[UUID],
        tenant_id: UUID | None,
        db: Session,
    ) -> list[FileRecord]:
        """校验每个 ID 存在、可用且属于当前租户，并锁定记录等待绑定。"""

        if len(file_ids) > MAX_FILES:
            raise FileValidationError(f"每张审批单最多关联 {MAX_FILES} 个文件")
        if len(set(file_ids)) != len(file_ids):
            raise FileValidationError("file_ids 中不能有重复 ID")
        if not file_ids:
            return []
        statement = (
            select(FileRecord)
            .where(FileRecord.id.in_(file_ids))
            .with_for_update()
        )
        by_id = {record.id: record for record in db.exec(statement).all()}
        records: list[FileRecord] = []
        for file_id in file_ids:
            record = by_id.get(file_id)
            if record is None:
                raise FileValidationError(f"file_id 不存在：{file_id}")
            if record.tenant_id != tenant_id or record.status != "READY":
                raise FileValidationError(f"file_id 不存在或无权使用：{file_id}")
            records.append(record)
        return records

    @staticmethod
    def bind_to_instance(
        instance_id: UUID,
        records: Sequence[FileRecord],
        db: Session,
    ) -> None:
        """把已校验文件加入当前审批发起事务，顺序与请求保持一致。"""

        for position, record in enumerate(records):
            db.add(
                ApprovalAttachment(
                    file_id=record.id,
                    approval_instance_id=instance_id,
                    position=position,
                )
            )

    @staticmethod
    def list_for_instance(instance_id: UUID, db: Session) -> list[FileRecord]:
        """按上传顺序读取审批单已经绑定的文件元数据。"""

        statement = (
            select(FileRecord)
            .join(ApprovalAttachment, ApprovalAttachment.file_id == FileRecord.id)
            .where(ApprovalAttachment.approval_instance_id == instance_id)
            .order_by(ApprovalAttachment.position)
        )
        return list(db.exec(statement).all())

    @staticmethod
    def get_for_download(
        file_id: UUID,
        tenant_id: UUID | None,
        db: Session,
        *,
        admin: bool = False,
    ) -> FileRecord:
        """验证文件存在和归属后返回下载元数据。"""

        record = db.get(FileRecord, file_id)
        if record is None or record.status != "READY":
            raise FileAccessError("file_id 不存在")
        if not admin and record.tenant_id != tenant_id:
            raise FileAccessError("file_id 不存在或无权访问")
        return record

    def open_content(self, record: FileRecord) -> BinaryIO:
        """打开通过权限校验的对象内容。"""

        return self.storage.open(record.object_key)
