-- 将已执行的统一任务表迁移调整为审批、抄送共用的接收人命名。
-- RENAME COLUMN 原地保留现有测试任务；不需要复制记录或兼容旧列。
BEGIN;

ALTER TABLE process.approval_task
    RENAME COLUMN approver_person_id TO recipient_person_id;

ALTER TABLE process.approval_task
    RENAME COLUMN approver_snapshot_json TO recipient_snapshot_json;

ALTER TABLE process.approval_task
    RENAME CONSTRAINT uq_approval_task_approver TO uq_approval_task_recipient;

ALTER INDEX process.ix_process_approval_task_approver_person_id
    RENAME TO ix_process_approval_task_recipient_person_id;

COMMENT ON COLUMN process.approval_task.recipient_person_id IS
    '任务接收人 ID，不建立跨 Schema 外键';
COMMENT ON COLUMN process.approval_task.recipient_snapshot_json IS
    '接收人当时的姓名等展示信息';

COMMIT;
