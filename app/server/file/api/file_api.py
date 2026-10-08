"""文件批量上传及租户、管理端下载接口。"""

from collections.abc import Iterator
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session

from app.common.db.postgres_db import get_postgres_engine
from app.common.schemas.result import Result
from app.common.security import verify_admin_key
from app.server.file.src.models import FileRecord
from app.server.file.src.service import (
    CHUNK_BYTES,
    FileAccessError,
    FileService,
    FileValidationError,
)
from app.server.tenant.api.dependencies import (
    BusinessAccessContext,
    use_business_access_context,
)


router = APIRouter()


class UploadedFileResponse(BaseModel):
    """一个已存储文件的可公开元数据。"""

    file_id: UUID
    file_name: str
    content_type: str
    size_bytes: int
    sha256: str
    uploaded_at: str


class BatchUploadResponse(BaseModel):
    """按请求顺序返回整批文件 ID 与对应元数据。"""

    file_ids: list[UUID]
    files: list[UploadedFileResponse]


def build_file_response(record: FileRecord) -> UploadedFileResponse:
    """把数据库文件记录转换为不暴露对象键的响应。"""

    return UploadedFileResponse(
        file_id=record.id,
        file_name=record.file_name,
        content_type=record.content_type,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        uploaded_at=record.uploaded_at.isoformat(),
    )


@router.post(
    "/files",
    response_model=Result[BatchUploadResponse],
    status_code=status.HTTP_201_CREATED,
    summary="批量上传审批附件",
)
def upload_files(
    files: list[UploadFile] = File(...),
    context: BusinessAccessContext = use_business_access_context(),
    db: Session = Depends(get_postgres_engine),
) -> Result[BatchUploadResponse]:
    """用可信租户身份整批上传文件，任一失败都不返回部分 ID。"""

    try:
        records = FileService().upload_many(files, context.tenant_id, db)
    except FileValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="文件存储暂时不可用") from exc
    finally:
        for upload in files:
            upload.file.close()
    return Result.success(
        BatchUploadResponse(
            file_ids=[record.id for record in records],
            files=[build_file_response(record) for record in records],
        )
    )


def stream_file(record: FileRecord) -> StreamingResponse:
    """鉴权完成后以附件方式分块输出文件，并确保对象流被关闭。"""

    service = FileService()
    try:
        content = service.open_content(record)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="文件内容暂时不可读取") from exc

    def chunks() -> Iterator[bytes]:
        """分块读取对象内容，响应结束时关闭底层存储流。"""

        try:
            while True:
                part = content.read(CHUNK_BYTES)
                if not part:
                    break
                yield part
        finally:
            content.close()

    encoded_name = quote(record.file_name, safe="")
    return StreamingResponse(
        chunks(),
        media_type=record.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
            "Content-Length": str(record.size_bytes),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/files/{file_id}/content", summary="业务方下载审批文件")
def download_business_file(
    file_id: UUID,
    context: BusinessAccessContext = use_business_access_context(),
    db: Session = Depends(get_postgres_engine),
) -> StreamingResponse:
    """按租户身份下载自己上传的文件。"""

    try:
        record = FileService.get_for_download(file_id, context.tenant_id, db)
    except FileAccessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return stream_file(record)


@router.get(
    "/admin/files/{file_id}/content",
    dependencies=[Depends(verify_admin_key)],
    summary="管理端下载审批文件",
)
def download_admin_file(
    file_id: UUID,
    db: Session = Depends(get_postgres_engine),
) -> StreamingResponse:
    """管理端按 ID 下载文件，供审批和抄送详情查看。"""

    try:
        record = FileService.get_for_download(file_id, None, db, admin=True)
    except FileAccessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return stream_file(record)
