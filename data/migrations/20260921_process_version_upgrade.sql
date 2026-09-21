-- 审批流定义由无版本结构升级为显式版本结构。
-- 本脚本面向当前开发库：旧流程表必须为空，发现数据时会主动中止，避免误删。

BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM process.approval_process LIMIT 1) THEN
        RAISE EXCEPTION 'process.approval_process 中存在数据，本升级脚本只允许在空表上执行';
    END IF;
END
$$;

DROP TABLE IF EXISTS process.approval_process_node;

ALTER TABLE process.approval_process
    DROP COLUMN IF EXISTS form_schema_json,
    DROP COLUMN IF EXISTS form_ui_schema_json,
    DROP COLUMN IF EXISTS orchestration_json;

CREATE TABLE process.approval_process_version (
    id UUID PRIMARY KEY,
    process_id UUID NOT NULL,
    version_no INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    name VARCHAR(128) NOT NULL,
    description VARCHAR(500),
    form_schema_json JSONB NOT NULL,
    form_ui_schema_json JSONB NOT NULL,
    orchestration_json JSONB NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    published_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT fk_approval_process_version_process
        FOREIGN KEY (process_id) REFERENCES process.approval_process (id),
    CONSTRAINT uq_approval_process_version_no
        UNIQUE (process_id, version_no),
    CONSTRAINT ck_approval_process_version_no_positive
        CHECK (version_no > 0),
    CONSTRAINT ck_approval_process_version_revision_non_negative
        CHECK (revision >= 0),
    CONSTRAINT ck_approval_process_version_status
        CHECK (status IN ('DRAFT', 'PUBLISHED'))
);

CREATE INDEX ix_process_approval_process_version_process_id
    ON process.approval_process_version (process_id);

CREATE INDEX ix_process_approval_process_version_status
    ON process.approval_process_version (status);

CREATE UNIQUE INDEX ux_process_approval_process_version_one_draft
    ON process.approval_process_version (process_id)
    WHERE status = 'DRAFT';

ALTER TABLE process.approval_process
    ADD COLUMN current_version_id UUID
    REFERENCES process.approval_process_version (id);

CREATE INDEX ix_process_approval_process_current_version_id
    ON process.approval_process (current_version_id);

CREATE TABLE process.approval_process_version_node (
    id UUID PRIMARY KEY,
    process_version_id UUID NOT NULL,
    node_definition_id UUID NOT NULL,
    node_type VARCHAR(32) NOT NULL,
    name VARCHAR(128) NOT NULL,
    config_json JSONB NOT NULL,
    position_json JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_approval_process_version_node_version
        FOREIGN KEY (process_version_id) REFERENCES process.approval_process_version (id),
    CONSTRAINT fk_approval_process_version_node_definition
        FOREIGN KEY (node_definition_id) REFERENCES process.node_definition (id)
);

CREATE INDEX ix_process_approval_process_version_node_version_id
    ON process.approval_process_version_node (process_version_id);

CREATE INDEX ix_process_approval_process_version_node_definition_id
    ON process.approval_process_version_node (node_definition_id);

CREATE INDEX ix_process_approval_process_version_node_type
    ON process.approval_process_version_node (node_type);

COMMENT ON TABLE process.approval_process IS '审批流稳定身份和当前发布版本';
COMMENT ON COLUMN process.approval_process.id IS '稳定的流程 ID，业务系统发起审批时传入';
COMMENT ON COLUMN process.approval_process.name IS '当前发布版本的流程名称，草稿流程使用初始名称';
COMMENT ON COLUMN process.approval_process.description IS '当前发布版本的流程说明';
COMMENT ON COLUMN process.approval_process.status IS '流程状态：DRAFT、ENABLED 或 DISABLED';
COMMENT ON COLUMN process.approval_process.current_version_id IS '当前已发布版本 ID，未首次发布时为空';
COMMENT ON COLUMN process.approval_process.created_at IS '创建时间';
COMMENT ON COLUMN process.approval_process.updated_at IS '最后更新时间';

COMMENT ON TABLE process.approval_process_version IS '审批流版本主体、表单和编排';
COMMENT ON COLUMN process.approval_process_version.id IS '流程版本主键 ID';
COMMENT ON COLUMN process.approval_process_version.process_id IS '所属稳定流程 ID';
COMMENT ON COLUMN process.approval_process_version.version_no IS '从 1 开始递增的版本号';
COMMENT ON COLUMN process.approval_process_version.status IS '版本状态：DRAFT 或 PUBLISHED';
COMMENT ON COLUMN process.approval_process_version.name IS '该版本内冻结的流程名称';
COMMENT ON COLUMN process.approval_process_version.description IS '该版本内冻结的流程说明';
COMMENT ON COLUMN process.approval_process_version.form_schema_json IS '该版本审批表单字段和校验规则';
COMMENT ON COLUMN process.approval_process_version.form_ui_schema_json IS '该版本审批表单展示规则';
COMMENT ON COLUMN process.approval_process_version.orchestration_json IS '该版本节点关系、条件和默认路径';
COMMENT ON COLUMN process.approval_process_version.revision IS '草稿乐观锁修订号，每次整图保存递增';
COMMENT ON COLUMN process.approval_process_version.created_at IS '版本创建时间';
COMMENT ON COLUMN process.approval_process_version.updated_at IS '版本最后更新时间';
COMMENT ON COLUMN process.approval_process_version.published_at IS '版本发布时间，草稿为空';

COMMENT ON TABLE process.approval_process_version_node IS '审批流版本中的具体节点和冻结配置';
COMMENT ON COLUMN process.approval_process_version_node.id IS '版本节点主键 ID';
COMMENT ON COLUMN process.approval_process_version_node.process_version_id IS '所属流程版本 ID';
COMMENT ON COLUMN process.approval_process_version_node.node_definition_id IS '来源节点能力定义 ID';
COMMENT ON COLUMN process.approval_process_version_node.node_type IS '发布时固化的后端执行类型';
COMMENT ON COLUMN process.approval_process_version_node.name IS '该版本中的节点名称';
COMMENT ON COLUMN process.approval_process_version_node.config_json IS '该版本中的节点功能配置，包含审批模式和审批人';
COMMENT ON COLUMN process.approval_process_version_node.position_json IS '前端画布坐标';
COMMENT ON COLUMN process.approval_process_version_node.created_at IS '创建时间';
COMMENT ON COLUMN process.approval_process_version_node.updated_at IS '最后更新时间';

COMMIT;
