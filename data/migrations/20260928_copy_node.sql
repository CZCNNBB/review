-- 第一阶段：既有库将审批和抄送统一保存到 process.approval_task。
-- 第二阶段通过 20260928_task_recipient_columns.sql 将任务接收人列统一命名。
-- 本脚本保留待部署时执行；不会由应用启动自动运行。
BEGIN;

ALTER TABLE process.approval_task
    ADD COLUMN IF NOT EXISTS task_type VARCHAR(20) NOT NULL DEFAULT 'APPROVAL';

ALTER TABLE process.approval_task
    ADD COLUMN IF NOT EXISTS extension_json JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE process.approval_task
    DROP CONSTRAINT IF EXISTS ck_approval_task_status;

ALTER TABLE process.approval_task
    ADD CONSTRAINT ck_approval_task_status
        CHECK (
            (task_type = 'APPROVAL' AND status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED'))
            OR (task_type = 'COPY' AND status = 'RECEIVED')
        );

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_approval_task_type'
          AND conrelid = 'process.approval_task'::regclass
    ) THEN
        ALTER TABLE process.approval_task
            ADD CONSTRAINT ck_approval_task_type
                CHECK (task_type IN ('APPROVAL', 'COPY'));
    END IF;
END $$;

-- 若旧版抄送表已经产生数据，保留每条记录原 ID，旧的详情链接仍可使用。
-- 校验完成后在同一事务中删除旧表；任何一条未迁成功都会回滚全部变更。
DO $$
BEGIN
    IF to_regclass('process.approval_copy') IS NOT NULL THEN
        INSERT INTO process.approval_task (
            id, instance_id, node_execution_id, approver_person_id,
            approver_snapshot_json, task_type, extension_json, status,
            created_at, updated_at
        )
        SELECT
            id, instance_id, node_execution_id, recipient_person_id,
            recipient_snapshot_json, 'COPY',
            '{"delivery_channel":"APPROVAL_CENTER"}'::jsonb,
            'RECEIVED', created_at, created_at
        FROM process.approval_copy
        ON CONFLICT (node_execution_id, approver_person_id) DO NOTHING;

        IF EXISTS (
            SELECT 1
            FROM process.approval_copy AS old_copy
            LEFT JOIN process.approval_task AS task ON task.id = old_copy.id
            WHERE task.id IS NULL OR task.task_type <> 'COPY'
        ) THEN
            RAISE EXCEPTION '旧抄送记录迁移不完整，已回滚';
        END IF;

        DROP TABLE process.approval_copy;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_process_approval_task_type_person_created
    ON process.approval_task (task_type, approver_person_id, created_at DESC);

COMMENT ON TABLE process.approval_task IS '审批与抄送共用的人员任务表';
COMMENT ON COLUMN process.approval_task.approver_person_id IS
    '任务接收人 ID，不建立跨 Schema 外键';
COMMENT ON COLUMN process.approval_task.approver_snapshot_json IS
    '接收人当时的姓名等展示信息';
COMMENT ON COLUMN process.approval_task.task_type IS '任务类型：APPROVAL 审批、COPY 抄送';
COMMENT ON COLUMN process.approval_task.extension_json IS '类型专有的附加信息';
COMMENT ON COLUMN process.approval_task.status IS
    '审批任务状态或抄送已送达状态 RECEIVED';

COMMIT;
