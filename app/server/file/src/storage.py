"""本地与 S3 兼容对象存储的统一接口。"""

import os
import shutil
from pathlib import Path
from typing import BinaryIO, Protocol


class FileStorage(Protocol):
    """定义文件模块需要的最小存储能力。"""

    def put(self, source: Path, object_key: str, content_type: str) -> None:
        """把临时文件写入不可公开读取的对象键。"""

    def open(self, object_key: str) -> BinaryIO:
        """打开文件内容，调用方负责关闭流。"""

    def delete(self, object_key: str) -> None:
        """删除未关联或上传失败的对象。"""


class LocalFileStorage:
    """开发环境使用的本地存储，根目录固定在 Git 项目之外。"""

    def __init__(self, root: Path | None = None):
        """初始化并创建本地文件根目录。"""

        configured = os.getenv("APPROVAL_FILE_LOCAL_ROOT")
        self.root = root or Path(configured or Path.home() / ".approval-center-files")
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, object_key: str) -> Path:
        """把服务端生成的对象键限制在配置的根目录内。"""

        target = (self.root / object_key).resolve()
        if not target.is_relative_to(self.root.resolve()):
            raise ValueError("文件对象键越过存储目录")
        return target

    def put(self, source: Path, object_key: str, content_type: str) -> None:
        """复制临时文件到对象目录，不使用用户提供的文件名。"""

        target = self._path(object_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    def open(self, object_key: str) -> BinaryIO:
        """以只读二进制模式打开已保存对象。"""

        return self._path(object_key).open("rb")

    def delete(self, object_key: str) -> None:
        """删除对象；不存在时保持幂等。"""

        self._path(object_key).unlink(missing_ok=True)


class S3FileStorage:
    """使用私有 S3 兼容存储桶保存审批附件。"""

    def __init__(self):
        """从服务端环境变量创建对象存储客户端。"""

        import boto3
        from botocore.config import Config

        self.bucket = os.environ["APPROVAL_FILE_S3_BUCKET"]
        provider = os.getenv("APPROVAL_FILE_S3_PROVIDER", "generic").strip().lower()
        if provider not in {"generic", "aliyun"}:
            raise ValueError(f"不支持的 S3 兼容存储供应商：{provider}")
        client_options = {
            "endpoint_url": os.getenv("APPROVAL_FILE_S3_ENDPOINT") or None,
            "region_name": os.getenv("APPROVAL_FILE_S3_REGION") or None,
        }
        if provider == "aliyun":
            # 阿里云 OSS 仅支持虚拟主机访问；boto3 上传需使用 S3 V2 签名，
            # 否则可能发送 OSS 不接受的 aws-chunked 请求。
            client_options["config"] = Config(
                signature_version="s3",
                s3={"addressing_style": "virtual"},
            )
        self.client = boto3.client(
            "s3",
            **client_options,
        )

    def put(self, source: Path, object_key: str, content_type: str) -> None:
        """上传私有对象并写入正确的媒体类型。"""

        self.client.upload_file(
            str(source),
            self.bucket,
            object_key,
            ExtraArgs={"ContentType": content_type},
        )

    def open(self, object_key: str) -> BinaryIO:
        """取得对象流，供鉴权通过后的下载接口转发。"""

        return self.client.get_object(Bucket=self.bucket, Key=object_key)["Body"]

    def delete(self, object_key: str) -> None:
        """删除对象；S3 删除不存在的键也视为成功。"""

        self.client.delete_object(Bucket=self.bucket, Key=object_key)


def create_storage() -> FileStorage:
    """按配置选择存储驱动，未显式配置时使用本地开发目录。"""

    driver = os.getenv("APPROVAL_FILE_STORAGE", "local").strip().lower()
    if driver == "local":
        return LocalFileStorage()
    if driver == "s3":
        return S3FileStorage()
    raise ValueError(f"不支持的文件存储驱动：{driver}")
