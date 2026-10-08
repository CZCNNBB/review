-- 新增审批附件元数据和关联表，不迁移或删除现有审批数据。
BEGIN;

CREATE SCHEMA IF NOT EXISTS file;

CREATE TABLE IF NOT EXISTS file.file_record (
    id UUID PRIMARY KEY,
    tenant_id UUID,
    object_key VARCHAR(500) NOT NULL UNIQUE,
    file_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(150) NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'READY',
    uploaded_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT ck_file_record_status CHECK (status IN ('READY', 'DELETING')),
    CONSTRAINT ck_file_record_size CHECK (size_bytes > 0)
);

CREATE INDEX IF NOT EXISTS ix_file_file_record_tenant_id
    ON file.file_record (tenant_id);
CREATE INDEX IF NOT EXISTS ix_file_file_record_status
    ON file.file_record (status);

CREATE TABLE IF NOT EXISTS file.approval_attachment (
    id UUID PRIMARY KEY,
    file_id UUID NOT NULL,
    approval_instance_id UUID NOT NULL,
    position INTEGER NOT NULL,
    attached_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_approval_attachment_file
        FOREIGN KEY (file_id) REFERENCES file.file_record (id),
    CONSTRAINT uq_approval_attachment_file UNIQUE (approval_instance_id, file_id),
    CONSTRAINT ck_approval_attachment_position CHECK (position >= 0)
);

CREATE INDEX IF NOT EXISTS ix_file_approval_attachment_file_id
    ON file.approval_attachment (file_id);
CREATE INDEX IF NOT EXISTS ix_file_approval_attachment_instance_id
    ON file.approval_attachment (approval_instance_id);

COMMENT ON TABLE file.file_record IS '业务方上传的不可变文件元数据，文件本体位于私有存储';
COMMENT ON TABLE file.approval_attachment IS '审批实例与申请材料的有序关联';

COMMIT;
