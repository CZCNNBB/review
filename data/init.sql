-- 审批中心统一数据库初始化脚本。
-- 所有语句保持幂等，适用于全新环境和结构已经一致的开发环境。

CREATE SCHEMA IF NOT EXISTS tenant;

CREATE TABLE IF NOT EXISTS tenant.tenant (
    id UUID PRIMARY KEY,
    code VARCHAR(64) NOT NULL,
    name VARCHAR(128) NOT NULL,
    description VARCHAR(500),
    callback_base_url VARCHAR(500) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_tenant_tenant_code
    ON tenant.tenant (code);

CREATE INDEX IF NOT EXISTS ix_tenant_tenant_status
    ON tenant.tenant (status);

CREATE TABLE IF NOT EXISTS tenant.tenant_api_key (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name VARCHAR(100) NOT NULL,
    api_key VARCHAR(128) NOT NULL,
    status VARCHAR(20) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE,
    last_used_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    CONSTRAINT fk_tenant_api_key_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenant.tenant (id)
);

CREATE INDEX IF NOT EXISTS ix_tenant_tenant_api_key_tenant_id
    ON tenant.tenant_api_key (tenant_id);

CREATE UNIQUE INDEX IF NOT EXISTS ix_tenant_tenant_api_key_api_key
    ON tenant.tenant_api_key (api_key);

CREATE INDEX IF NOT EXISTS ix_tenant_tenant_api_key_status
    ON tenant.tenant_api_key (status);

-- 回调认证方案为 Service Token：业务系统为自己现有的认证机制创建一个服务账号，为
-- 审批中心签发长期 Token。审批中心复用业务系统已有的认证请求头，不要求业务系统新增
-- 审批中心专用的认证协议。回调时 Token 必须能够原样还原，因此保存应用主密钥加密后的
-- 密文，不能只保存哈希。
--
-- 早期 HMAC 凭据结构到本结构的升级脚本见
-- data/migrations/20260922_callback_credential_service_token.sql，已有开发库需要先执行该脚本。
CREATE TABLE IF NOT EXISTS tenant.tenant_callback_credential (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name VARCHAR(100) NOT NULL,
    header_name VARCHAR(100) NOT NULL,
    token_prefix VARCHAR(50) NOT NULL,
    token_ciphertext TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    CONSTRAINT fk_tenant_callback_credential_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenant.tenant (id),
    CONSTRAINT ck_tenant_callback_credential_status
        CHECK (status IN ('ACTIVE', 'REVOKED'))
);

CREATE INDEX IF NOT EXISTS ix_tenant_tenant_callback_credential_tenant_id
    ON tenant.tenant_callback_credential (tenant_id);

CREATE INDEX IF NOT EXISTS ix_tenant_tenant_callback_credential_status
    ON tenant.tenant_callback_credential (status);

-- 一个租户同一时间只允许存在一个 ACTIVE 回调凭据。更换 Token 时必须在同一个事务中
-- 撤销旧凭据并写入新凭据，避免出现两个有效凭据或没有可用凭据的中间状态。
CREATE UNIQUE INDEX IF NOT EXISTS ux_tenant_callback_credential_one_active
    ON tenant.tenant_callback_credential (tenant_id)
    WHERE status = 'ACTIVE';

-- ============================================================================
-- 租户业务接入绑定表：流程授权、业务动作授权和审批使用记录。
-- 三张表只保存租户与业务资源的归属关系，业务资源 ID 不建立跨 Schema 外键，
-- 删除 tenant Schema 后 process 和 integration 模块仍然可以独立运行。
-- ============================================================================

-- 流程授权只表达租户可以使用哪条审批流，不保存流程版本、节点或审批人配置。
CREATE TABLE IF NOT EXISTS tenant.process_binding (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    process_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_process_binding_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenant.tenant (id),
    CONSTRAINT uq_process_binding_resource
        UNIQUE (tenant_id, process_id),
    CONSTRAINT ck_process_binding_status
        CHECK (status IN ('ENABLED', 'DISABLED'))
);

CREATE INDEX IF NOT EXISTS ix_tenant_process_binding_tenant_id
    ON tenant.process_binding (tenant_id);

CREATE INDEX IF NOT EXISTS ix_tenant_process_binding_process_id
    ON tenant.process_binding (process_id);

CREATE INDEX IF NOT EXISTS ix_tenant_process_binding_status
    ON tenant.process_binding (status);

-- 业务动作授权只控制租户能否使用某个动作，动作的接口配置仍保存在 integration Schema。
CREATE TABLE IF NOT EXISTS tenant.business_action_binding (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    business_action_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_business_action_binding_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenant.tenant (id),
    CONSTRAINT uq_business_action_binding_resource
        UNIQUE (tenant_id, business_action_id),
    CONSTRAINT ck_business_action_binding_status
        CHECK (status IN ('ENABLED', 'DISABLED'))
);

CREATE INDEX IF NOT EXISTS ix_tenant_business_action_binding_tenant_id
    ON tenant.business_action_binding (tenant_id);

CREATE INDEX IF NOT EXISTS ix_tenant_business_action_binding_action_id
    ON tenant.business_action_binding (business_action_id);

CREATE INDEX IF NOT EXISTS ix_tenant_business_action_binding_status
    ON tenant.business_action_binding (status);

-- 使用记录保存某租户实际发起过某次审批的事实，同时作为按租户查询审批实例的入口。
-- 该表只保存归属和关联信息，不重复保存审批状态、当前节点和耗时，这些数据统一从
-- process 运行表读取，避免同一份状态出现两份不一致的副本。
CREATE TABLE IF NOT EXISTS tenant.process_usage_record (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    process_id UUID NOT NULL,
    process_version_id UUID NOT NULL,
    approval_instance_id UUID NOT NULL,
    business_key VARCHAR(200) NOT NULL,
    action_code VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_process_usage_record_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenant.tenant (id),
    CONSTRAINT uq_process_usage_record_instance
        UNIQUE (approval_instance_id),
    CONSTRAINT uq_process_usage_record_business_key
        UNIQUE (tenant_id, process_id, business_key)
);

CREATE INDEX IF NOT EXISTS ix_tenant_process_usage_record_tenant_id
    ON tenant.process_usage_record (tenant_id);

CREATE INDEX IF NOT EXISTS ix_tenant_process_usage_record_process_id
    ON tenant.process_usage_record (process_id);

CREATE INDEX IF NOT EXISTS ix_tenant_process_usage_record_instance_id
    ON tenant.process_usage_record (approval_instance_id);

CREATE INDEX IF NOT EXISTS ix_tenant_process_usage_record_business_key
    ON tenant.process_usage_record (business_key);

CREATE INDEX IF NOT EXISTS ix_tenant_process_usage_record_action_code
    ON tenant.process_usage_record (action_code);

CREATE INDEX IF NOT EXISTS ix_tenant_process_usage_record_created_at
    ON tenant.process_usage_record (created_at);

-- 人员绑定不引用 organization Schema，tenant Schema 可以独立移除。
CREATE TABLE IF NOT EXISTS tenant.person_binding (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    person_id UUID NOT NULL,
    employee_no VARCHAR(64),
    external_user_id VARCHAR(128),
    display_name VARCHAR(100),
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_person_binding_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenant.tenant (id),
    CONSTRAINT uq_person_binding_resource
        UNIQUE (tenant_id, person_id),
    CONSTRAINT uq_person_binding_employee_no
        UNIQUE (tenant_id, employee_no),
    CONSTRAINT uq_person_binding_external_user
        UNIQUE (tenant_id, external_user_id)
);

CREATE INDEX IF NOT EXISTS ix_tenant_person_binding_tenant_id
    ON tenant.person_binding (tenant_id);

CREATE INDEX IF NOT EXISTS ix_tenant_person_binding_person_id
    ON tenant.person_binding (person_id);

CREATE INDEX IF NOT EXISTS ix_tenant_person_binding_status
    ON tenant.person_binding (status);

CREATE SCHEMA IF NOT EXISTS organization;

CREATE TABLE IF NOT EXISTS organization.person (
    id UUID PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    mobile VARCHAR(32),
    email VARCHAR(255),
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_organization_person_name
    ON organization.person (name);

CREATE INDEX IF NOT EXISTS ix_organization_person_status
    ON organization.person (status);

CREATE TABLE IF NOT EXISTS organization.department (
    id UUID PRIMARY KEY,
    code VARCHAR(64) NOT NULL,
    name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_organization_department_code
    ON organization.department (code);

CREATE INDEX IF NOT EXISTS ix_organization_department_status
    ON organization.department (status);

CREATE TABLE IF NOT EXISTS organization.department_member (
    id UUID PRIMARY KEY,
    department_id UUID NOT NULL,
    person_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_department_member_department
        FOREIGN KEY (department_id) REFERENCES organization.department (id),
    CONSTRAINT fk_department_member_person
        FOREIGN KEY (person_id) REFERENCES organization.person (id),
    CONSTRAINT uq_department_member_person
        UNIQUE (department_id, person_id)
);

CREATE INDEX IF NOT EXISTS ix_organization_department_member_department_id
    ON organization.department_member (department_id);

CREATE INDEX IF NOT EXISTS ix_organization_department_member_person_id
    ON organization.department_member (person_id);

CREATE INDEX IF NOT EXISTS ix_organization_department_member_status
    ON organization.department_member (status);

CREATE SCHEMA IF NOT EXISTS process;

-- 节点能力定义只描述系统支持什么节点，不保存某条流程中的具体节点、审批人或位置。
CREATE TABLE IF NOT EXISTS process.node_definition (
    id UUID PRIMARY KEY,
    node_type VARCHAR(32) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500),
    icon VARCHAR(100),
    config_schema_json JSONB NOT NULL,
    ui_schema_json JSONB NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_process_node_definition_node_type
    ON process.node_definition (node_type);

-- 已初始化的开发库即使保留旧普通索引，也会由本唯一索引提供并发一致性保证。
CREATE UNIQUE INDEX IF NOT EXISTS ux_process_node_definition_name
    ON process.node_definition (name);

CREATE INDEX IF NOT EXISTS ix_process_node_definition_status
    ON process.node_definition (status);

-- 流程主体只保存稳定身份和当前发布版本，表单与编排保存在版本表。
CREATE TABLE IF NOT EXISTS process.approval_process (
    id UUID PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    description VARCHAR(500),
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_process_approval_process_name
    ON process.approval_process (name);

CREATE INDEX IF NOT EXISTS ix_process_approval_process_status
    ON process.approval_process (status);

-- 每个版本保存一份完整表单和编排，发布后由业务层保证不可修改。
CREATE TABLE IF NOT EXISTS process.approval_process_version (
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

CREATE INDEX IF NOT EXISTS ix_process_approval_process_version_process_id
    ON process.approval_process_version (process_id);

CREATE INDEX IF NOT EXISTS ix_process_approval_process_version_status
    ON process.approval_process_version (status);

-- 同一流程最多只有一个草稿版本。
CREATE UNIQUE INDEX IF NOT EXISTS ux_process_approval_process_version_one_draft
    ON process.approval_process_version (process_id)
    WHERE status = 'DRAFT';

-- 先创建版本表，再补当前版本外键，解决两张表的循环引用顺序。
ALTER TABLE process.approval_process
    ADD COLUMN IF NOT EXISTS current_version_id UUID
    REFERENCES process.approval_process_version (id);

CREATE INDEX IF NOT EXISTS ix_process_approval_process_current_version_id
    ON process.approval_process (current_version_id);

-- 版本节点单独存表，便于按版本查询、约束和关联后续节点执行记录。
CREATE TABLE IF NOT EXISTS process.approval_process_version_node (
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

CREATE INDEX IF NOT EXISTS ix_process_approval_process_version_node_version_id
    ON process.approval_process_version_node (process_version_id);

CREATE INDEX IF NOT EXISTS ix_process_approval_process_version_node_definition_id
    ON process.approval_process_version_node (node_definition_id);

CREATE INDEX IF NOT EXISTS ix_process_approval_process_version_node_type
    ON process.approval_process_version_node (node_type);

-- ============================================================================
-- 审批运行表：审批实例、节点执行、审批任务和审批记录。
-- 运行表不保存 tenant_id，也不建立指向 tenant Schema 的外键。
-- ============================================================================

-- 实例在发起时绑定确定的已发布版本，后续发布新版本不影响已经运行的实例。
CREATE TABLE IF NOT EXISTS process.approval_instance (
    id UUID PRIMARY KEY,
    process_id UUID NOT NULL,
    process_version_id UUID NOT NULL,
    business_key VARCHAR(200) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    request_digest VARCHAR(64),
    title VARCHAR(200) NOT NULL,
    applicant_person_id UUID,
    applicant_snapshot_json JSONB NOT NULL,
    approval_form_json JSONB NOT NULL,
    execution_payload_json JSONB NOT NULL,
    action_code VARCHAR(100),
    status VARCHAR(20) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    finished_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_approval_instance_process
        FOREIGN KEY (process_id) REFERENCES process.approval_process (id),
    CONSTRAINT fk_approval_instance_process_version
        FOREIGN KEY (process_version_id) REFERENCES process.approval_process_version (id),
    CONSTRAINT uq_approval_instance_idempotency_key
        UNIQUE (idempotency_key),
    CONSTRAINT ck_approval_instance_status
        CHECK (status IN ('RUNNING', 'APPROVED', 'REJECTED', 'CANCELLED', 'ERROR'))
);

CREATE INDEX IF NOT EXISTS ix_process_approval_instance_process_id
    ON process.approval_instance (process_id);

CREATE INDEX IF NOT EXISTS ix_process_approval_instance_process_version_id
    ON process.approval_instance (process_version_id);

CREATE INDEX IF NOT EXISTS ix_process_approval_instance_business_key
    ON process.approval_instance (business_key);

CREATE INDEX IF NOT EXISTS ix_process_approval_instance_idempotency_key
    ON process.approval_instance (idempotency_key);

CREATE INDEX IF NOT EXISTS ix_process_approval_instance_applicant_person_id
    ON process.approval_instance (applicant_person_id);

CREATE INDEX IF NOT EXISTS ix_process_approval_instance_status
    ON process.approval_instance (status);

-- 已经建过运行表的库补上请求摘要列；全新库由上面的建表语句直接创建。
ALTER TABLE process.approval_instance
    ADD COLUMN IF NOT EXISTS request_digest VARCHAR(64);

-- 节点执行表直接支持后台展示当前节点、节点耗时和实际选择的分支。
CREATE TABLE IF NOT EXISTS process.approval_node_execution (
    id UUID PRIMARY KEY,
    instance_id UUID NOT NULL,
    process_version_id UUID NOT NULL,
    node_id UUID NOT NULL,
    node_type VARCHAR(32) NOT NULL,
    node_name VARCHAR(128) NOT NULL,
    sequence_no INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    entered_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    next_node_id UUID,
    result_json JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_approval_node_execution_instance
        FOREIGN KEY (instance_id) REFERENCES process.approval_instance (id),
    CONSTRAINT fk_approval_node_execution_process_version
        FOREIGN KEY (process_version_id) REFERENCES process.approval_process_version (id),
    CONSTRAINT fk_approval_node_execution_node
        FOREIGN KEY (node_id) REFERENCES process.approval_process_version_node (id),
    CONSTRAINT uq_approval_node_execution_sequence
        UNIQUE (instance_id, sequence_no),
    CONSTRAINT ck_approval_node_execution_sequence_positive
        CHECK (sequence_no > 0),
    CONSTRAINT ck_approval_node_execution_status
        CHECK (status IN ('ACTIVE', 'COMPLETED', 'REJECTED', 'CANCELLED', 'ERROR'))
);

CREATE INDEX IF NOT EXISTS ix_process_approval_node_execution_instance_id
    ON process.approval_node_execution (instance_id);

CREATE INDEX IF NOT EXISTS ix_process_approval_node_execution_process_version_id
    ON process.approval_node_execution (process_version_id);

CREATE INDEX IF NOT EXISTS ix_process_approval_node_execution_node_id
    ON process.approval_node_execution (node_id);

CREATE INDEX IF NOT EXISTS ix_process_approval_node_execution_node_type
    ON process.approval_node_execution (node_type);

CREATE INDEX IF NOT EXISTS ix_process_approval_node_execution_status
    ON process.approval_node_execution (status);

-- 同一实例同时最多存在一条 ACTIVE 节点执行记录，由部分唯一索引兜住并发推进。
CREATE UNIQUE INDEX IF NOT EXISTS ux_process_approval_node_execution_one_active
    ON process.approval_node_execution (instance_id)
    WHERE status = 'ACTIVE';

-- 实例指向当前活动节点的列在两张表都建好后再补，解决循环引用顺序。
ALTER TABLE process.approval_instance
    ADD COLUMN IF NOT EXISTS current_node_execution_id UUID
    REFERENCES process.approval_node_execution (id);

CREATE INDEX IF NOT EXISTS ix_process_approval_instance_current_node_execution_id
    ON process.approval_instance (current_node_execution_id);

-- 进入人工审批节点时为全部审批人同时创建任务，节点内不存在顺序约束。
CREATE TABLE IF NOT EXISTS process.approval_task (
    id UUID PRIMARY KEY,
    instance_id UUID NOT NULL,
    node_execution_id UUID NOT NULL,
    approver_person_id UUID NOT NULL,
    approver_snapshot_json JSONB NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    handled_at TIMESTAMP WITH TIME ZONE,
    cancelled_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_approval_task_instance
        FOREIGN KEY (instance_id) REFERENCES process.approval_instance (id),
    CONSTRAINT fk_approval_task_node_execution
        FOREIGN KEY (node_execution_id) REFERENCES process.approval_node_execution (id),
    CONSTRAINT uq_approval_task_approver
        UNIQUE (node_execution_id, approver_person_id),
    CONSTRAINT ck_approval_task_status
        CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED'))
);

CREATE INDEX IF NOT EXISTS ix_process_approval_task_instance_id
    ON process.approval_task (instance_id);

CREATE INDEX IF NOT EXISTS ix_process_approval_task_node_execution_id
    ON process.approval_task (node_execution_id);

CREATE INDEX IF NOT EXISTS ix_process_approval_task_approver_person_id
    ON process.approval_task (approver_person_id);

CREATE INDEX IF NOT EXISTS ix_process_approval_task_status
    ON process.approval_task (status);

-- 审批记录不可修改，一个任务只能产生一条最终记录。
CREATE TABLE IF NOT EXISTS process.approval_record (
    id UUID PRIMARY KEY,
    instance_id UUID NOT NULL,
    node_execution_id UUID NOT NULL,
    task_id UUID NOT NULL,
    operator_person_id UUID NOT NULL,
    operator_snapshot_json JSONB NOT NULL,
    action VARCHAR(20) NOT NULL,
    comment TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_approval_record_instance
        FOREIGN KEY (instance_id) REFERENCES process.approval_instance (id),
    CONSTRAINT fk_approval_record_node_execution
        FOREIGN KEY (node_execution_id) REFERENCES process.approval_node_execution (id),
    CONSTRAINT fk_approval_record_task
        FOREIGN KEY (task_id) REFERENCES process.approval_task (id),
    CONSTRAINT uq_approval_record_task
        UNIQUE (task_id),
    CONSTRAINT ck_approval_record_action
        CHECK (action IN ('APPROVE', 'REJECT'))
);

CREATE INDEX IF NOT EXISTS ix_process_approval_record_instance_id
    ON process.approval_record (instance_id);

CREATE INDEX IF NOT EXISTS ix_process_approval_record_node_execution_id
    ON process.approval_record (node_execution_id);

CREATE INDEX IF NOT EXISTS ix_process_approval_record_task_id
    ON process.approval_record (task_id);

CREATE INDEX IF NOT EXISTS ix_process_approval_record_operator_person_id
    ON process.approval_record (operator_person_id);

CREATE INDEX IF NOT EXISTS ix_process_approval_record_action
    ON process.approval_record (action);

-- ============================================================================
-- 业务执行表：审批最终通过后的唯一一次业务系统调用及其结果。
-- 一条记录既表示待执行任务，也保存调用结果。第一版没有重试，因此不拆分任务表和尝试表。
-- 本表不保存 tenant_id，也不建立指向 tenant Schema 的外键：执行器通过 approval_instance_id
-- 和租户使用记录确定租户，关闭租户能力后审批运行模块仍然可以独立工作。
-- ============================================================================

-- approval_instance_id 唯一，同一个审批实例最多产生一条执行记录。
CREATE TABLE IF NOT EXISTS process.business_execution_record (
    id UUID PRIMARY KEY,
    approval_instance_id UUID NOT NULL,
    business_action_id UUID,
    action_code VARCHAR(100) NOT NULL,
    request_url VARCHAR(1000),
    http_method VARCHAR(10),
    relative_path VARCHAR(500),
    success_status_codes_json JSONB,
    timeout_ms INTEGER,
    request_payload_json JSONB NOT NULL,
    status VARCHAR(20) NOT NULL,
    http_status_code INTEGER,
    response_body TEXT,
    error_message VARCHAR(1000),
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_business_execution_record_instance
        FOREIGN KEY (approval_instance_id) REFERENCES process.approval_instance (id),
    CONSTRAINT uq_business_execution_record_instance
        UNIQUE (approval_instance_id),
    CONSTRAINT ck_business_execution_record_status
        CHECK (status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED'))
);

CREATE INDEX IF NOT EXISTS ix_process_business_execution_record_instance_id
    ON process.business_execution_record (approval_instance_id);

CREATE INDEX IF NOT EXISTS ix_process_business_execution_record_action_id
    ON process.business_execution_record (business_action_id);

CREATE INDEX IF NOT EXISTS ix_process_business_execution_record_action_code
    ON process.business_execution_record (action_code);

-- 后台轮询只查询 PENDING 记录，状态索引直接支撑 Worker 的领取语句。
CREATE INDEX IF NOT EXISTS ix_process_business_execution_record_status
    ON process.business_execution_record (status);

CREATE INDEX IF NOT EXISTS ix_process_business_execution_record_created_at
    ON process.business_execution_record (created_at);

-- ============================================================================
-- 业务接入表：审批通过后可以执行的一类业务动作及其参数规则。
-- 业务动作不保存 tenant_id，租户能否使用某个动作由 tenant.business_action_binding 决定。
-- 本模块只定义动作和校验参数，不执行任何外部 HTTP 请求。
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS integration;

-- 业务动作使用稳定的 action_code，与审批流相互独立，同一个动作可以被多条审批流使用。
CREATE TABLE IF NOT EXISTS integration.business_action (
    id UUID PRIMARY KEY,
    action_code VARCHAR(100) NOT NULL,
    name VARCHAR(128) NOT NULL,
    description VARCHAR(500),
    http_method VARCHAR(10) NOT NULL,
    relative_path VARCHAR(500) NOT NULL,
    request_schema_json JSONB NOT NULL,
    success_status_codes_json JSONB NOT NULL,
    timeout_ms INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_business_action_code
        UNIQUE (action_code),
    CONSTRAINT ck_business_action_http_method
        CHECK (http_method IN ('POST', 'PUT', 'PATCH')),
    CONSTRAINT ck_business_action_status
        CHECK (status IN ('ENABLED', 'DISABLED')),
    CONSTRAINT ck_business_action_timeout_positive
        CHECK (timeout_ms > 0),
    -- 相对路径必须以单个斜杠开头，且不能保存完整 URL 或协议相对地址，
    -- 保证最终地址只能由租户 callback_base_url 和本字段拼接得到。
    CONSTRAINT ck_business_action_relative_path
        CHECK (
            relative_path LIKE '/%'
            AND relative_path NOT LIKE '//%'
            AND relative_path NOT LIKE '%://%'
        )
);

CREATE INDEX IF NOT EXISTS ix_integration_business_action_action_code
    ON integration.business_action (action_code);

CREATE INDEX IF NOT EXISTS ix_integration_business_action_status
    ON integration.business_action (status);

CREATE INDEX IF NOT EXISTS ix_integration_business_action_name
    ON integration.business_action (name);

-- 第一批节点能力定义使用固定 UUID，方便前端画布和联调环境稳定引用。
-- 语句内部不允许出现分号，初始化脚本会按分号拆分后逐条执行。
INSERT INTO process.node_definition (
    id,
    node_type,
    name,
    description,
    icon,
    config_schema_json,
    ui_schema_json,
    status,
    created_at,
    updated_at
)
VALUES
    (
        '00000000-0000-0000-0000-000000000101',
        'START',
        '开始',
        '流程入口节点，每条流程必须且只能有一个开始节点',
        'play-circle',
        '{
            "type": "object",
            "title": "开始",
            "additionalProperties": false,
            "properties": {}
        }',
        '{
            "ui:order": []
        }',
        'ENABLED',
        NOW(),
        NOW()
    ),
    (
        '00000000-0000-0000-0000-000000000102',
        'APPROVAL',
        '人工审批',
        '人工审批节点，配置审批模式和审批人，进入节点时同时为全部审批人创建待办任务',
        'user-check',
        '{
            "type": "object",
            "title": "人工审批",
            "additionalProperties": false,
            "required": ["approval_mode", "approvers"],
            "properties": {
                "approval_mode": {
                    "type": "string",
                    "title": "审批模式",
                    "description": "AND 表示所有人同意后通过，OR 表示任意一人同意即通过",
                    "enum": ["AND", "OR"]
                },
                "approvers": {
                    "type": "array",
                    "title": "审批人",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": false,
                        "required": ["person_id"],
                        "properties": {
                            "person_id": {
                                "type": "string",
                                "format": "uuid",
                                "title": "人员 ID"
                            }
                        }
                    }
                }
            }
        }',
        '{
            "approval_mode": {"ui:widget": "select"},
            "approvers": {"ui:widget": "person-select"}
        }',
        'ENABLED',
        NOW(),
        NOW()
    ),
    (
        '00000000-0000-0000-0000-000000000103',
        'END',
        '结束',
        '流程正常的最终出口，走到这里就是审批通过、流程完成，节点本身没有配置项。审批被拒绝时实例在人工审批节点当场结束，不会走到结束节点。',
        'flag',
        '{
            "type": "object",
            "title": "结束",
            "additionalProperties": false,
            "properties": {}
        }',
        '{
            "ui:order": []
        }',
        'ENABLED',
        NOW(),
        NOW()
    ),
    (
        '00000000-0000-0000-0000-000000000104',
        'CONDITION',
        '条件分支',
        '按审批表单里的字段判断走哪条路，本身不产生审批任务。分支条件和去向在节点的分支编辑器里配置，进入后立即选路。',
        'git-branch',
        '{
            "type": "object",
            "title": "条件分支",
            "additionalProperties": false,
            "properties": {}
        }',
        '{
            "ui:order": []
        }',
        'ENABLED',
        NOW(),
        NOW()
    )
ON CONFLICT (id) DO NOTHING;

-- ============================================================================
-- Schema、数据表和字段说明
-- PostgreSQL 的 COMMENT 语句可以重复执行，用于保证全新库和已有开发库的注释一致。
-- ============================================================================

COMMENT ON SCHEMA tenant IS '租户、业务系统凭据及租户资源绑定数据';
COMMENT ON SCHEMA organization IS '审批中心全局人员、部门及部门成员数据';
COMMENT ON SCHEMA process IS '审批流定义、显式版本和后续审批运行数据';
COMMENT ON SCHEMA integration IS '业务动作定义、请求参数规则及调用配置';

COMMENT ON TABLE tenant.tenant IS '接入审批中心的业务系统租户';
COMMENT ON COLUMN tenant.tenant.id IS '租户主键 ID';
COMMENT ON COLUMN tenant.tenant.code IS '租户唯一编码';
COMMENT ON COLUMN tenant.tenant.name IS '租户名称';
COMMENT ON COLUMN tenant.tenant.description IS '租户说明';
COMMENT ON COLUMN tenant.tenant.callback_base_url IS '租户默认业务回调基础地址';
COMMENT ON COLUMN tenant.tenant.status IS '租户状态：ENABLED 或 DISABLED';
COMMENT ON COLUMN tenant.tenant.created_at IS '创建时间';
COMMENT ON COLUMN tenant.tenant.updated_at IS '最后更新时间';

COMMENT ON TABLE tenant.tenant_api_key IS '业务系统调用审批中心时使用的 API Key';
COMMENT ON COLUMN tenant.tenant_api_key.id IS 'API Key 记录主键 ID';
COMMENT ON COLUMN tenant.tenant_api_key.tenant_id IS '所属租户 ID';
COMMENT ON COLUMN tenant.tenant_api_key.name IS 'API Key 用途名称';
COMMENT ON COLUMN tenant.tenant_api_key.api_key IS 'API Key 明文值';
COMMENT ON COLUMN tenant.tenant_api_key.status IS 'API Key 状态：ENABLED 或 REVOKED';
COMMENT ON COLUMN tenant.tenant_api_key.expires_at IS '过期时间，为空表示长期有效';
COMMENT ON COLUMN tenant.tenant_api_key.last_used_at IS '最后一次认证成功时间';
COMMENT ON COLUMN tenant.tenant_api_key.created_at IS '创建时间';
COMMENT ON COLUMN tenant.tenant_api_key.revoked_at IS '撤销时间';
COMMENT ON COLUMN tenant.tenant_api_key.created_by IS '创建操作人 ID，初期允许为空';

COMMENT ON TABLE tenant.tenant_callback_credential IS '审批中心回调业务系统时使用的 Service Token 凭据';
COMMENT ON COLUMN tenant.tenant_callback_credential.id IS '回调凭据主键 ID';
COMMENT ON COLUMN tenant.tenant_callback_credential.tenant_id IS '所属租户 ID';
COMMENT ON COLUMN tenant.tenant_callback_credential.name IS '回调凭据用途名称';
COMMENT ON COLUMN tenant.tenant_callback_credential.header_name IS '业务系统现有的认证请求头名称，默认为 Authorization';
COMMENT ON COLUMN tenant.tenant_callback_credential.token_prefix IS 'Token 前缀，例如 Bearer；允许为空表示直接发送 Token 明文';
COMMENT ON COLUMN tenant.tenant_callback_credential.token_ciphertext IS '使用应用主密钥加密后的 Service Token，回调时解密还原';
COMMENT ON COLUMN tenant.tenant_callback_credential.status IS '回调凭据状态：ACTIVE 或 REVOKED，一个租户最多一条 ACTIVE 记录';
COMMENT ON COLUMN tenant.tenant_callback_credential.expires_at IS '过期时间，为空表示长期有效';
COMMENT ON COLUMN tenant.tenant_callback_credential.created_at IS '创建时间';
COMMENT ON COLUMN tenant.tenant_callback_credential.revoked_at IS '撤销时间';
COMMENT ON COLUMN tenant.tenant_callback_credential.created_by IS '创建操作人 ID，初期允许为空';

COMMENT ON TABLE tenant.process_binding IS '租户可以使用的审批流授权';
COMMENT ON COLUMN tenant.process_binding.id IS '流程授权主键 ID';
COMMENT ON COLUMN tenant.process_binding.tenant_id IS '所属租户 ID';
COMMENT ON COLUMN tenant.process_binding.process_id IS '关联的 process.approval_process ID，不建立跨 Schema 外键';
COMMENT ON COLUMN tenant.process_binding.status IS '授权状态：ENABLED 或 DISABLED，停用后不能新发起审批';
COMMENT ON COLUMN tenant.process_binding.created_at IS '创建时间';
COMMENT ON COLUMN tenant.process_binding.updated_at IS '最后更新时间';

COMMENT ON TABLE tenant.business_action_binding IS '租户可以使用的业务动作授权';
COMMENT ON COLUMN tenant.business_action_binding.id IS '业务动作授权主键 ID';
COMMENT ON COLUMN tenant.business_action_binding.tenant_id IS '所属租户 ID';
COMMENT ON COLUMN tenant.business_action_binding.business_action_id IS '关联的 integration.business_action ID，不建立跨 Schema 外键';
COMMENT ON COLUMN tenant.business_action_binding.status IS '授权状态：ENABLED 或 DISABLED，停用后不能用于新申请';
COMMENT ON COLUMN tenant.business_action_binding.created_at IS '创建时间';
COMMENT ON COLUMN tenant.business_action_binding.updated_at IS '最后更新时间';

COMMENT ON TABLE tenant.process_usage_record IS '租户实际发起审批的使用记录，同时作为按租户查询审批实例的作用域入口';
COMMENT ON COLUMN tenant.process_usage_record.id IS '使用记录主键 ID';
COMMENT ON COLUMN tenant.process_usage_record.tenant_id IS '发起审批的租户 ID';
COMMENT ON COLUMN tenant.process_usage_record.process_id IS '发起时使用的稳定流程 ID';
COMMENT ON COLUMN tenant.process_usage_record.process_version_id IS '发起时实际绑定的流程版本 ID';
COMMENT ON COLUMN tenant.process_usage_record.approval_instance_id IS '对应的 process.approval_instance ID，不建立跨 Schema 外键';
COMMENT ON COLUMN tenant.process_usage_record.business_key IS '业务系统中的原单据标识，与租户和流程共同构成幂等范围';
COMMENT ON COLUMN tenant.process_usage_record.action_code IS '审批通过后需要执行的业务动作标识，为空表示不触发业务执行';
COMMENT ON COLUMN tenant.process_usage_record.created_at IS '审批发起时间';

COMMENT ON TABLE tenant.person_binding IS '租户与全局人员的绑定关系及租户内人员扩展资料';
COMMENT ON COLUMN tenant.person_binding.id IS '人员绑定主键 ID';
COMMENT ON COLUMN tenant.person_binding.tenant_id IS '所属租户 ID';
COMMENT ON COLUMN tenant.person_binding.person_id IS '关联的 organization.person ID，不建立跨 Schema 外键';
COMMENT ON COLUMN tenant.person_binding.employee_no IS '人员在当前租户内的工号';
COMMENT ON COLUMN tenant.person_binding.external_user_id IS '人员在外部项目平台中的用户标识';
COMMENT ON COLUMN tenant.person_binding.display_name IS '人员在当前租户内的展示名称';
COMMENT ON COLUMN tenant.person_binding.status IS '绑定状态：ENABLED 或 DISABLED';
COMMENT ON COLUMN tenant.person_binding.created_at IS '创建时间';
COMMENT ON COLUMN tenant.person_binding.updated_at IS '最后更新时间';

COMMENT ON TABLE organization.person IS '审批中心统一维护的全局人员资料';
COMMENT ON COLUMN organization.person.id IS '人员主键 ID';
COMMENT ON COLUMN organization.person.name IS '人员姓名';
COMMENT ON COLUMN organization.person.mobile IS '手机号码，仅作为人员资料';
COMMENT ON COLUMN organization.person.email IS '电子邮箱，仅作为人员资料';
COMMENT ON COLUMN organization.person.status IS '人员状态：ENABLED 或 DISABLED';
COMMENT ON COLUMN organization.person.created_at IS '创建时间';
COMMENT ON COLUMN organization.person.updated_at IS '最后更新时间';

COMMENT ON TABLE organization.department IS '审批中心统一维护的全局平铺部门';
COMMENT ON COLUMN organization.department.id IS '部门主键 ID';
COMMENT ON COLUMN organization.department.code IS '全局唯一部门编码';
COMMENT ON COLUMN organization.department.name IS '部门名称';
COMMENT ON COLUMN organization.department.status IS '部门状态：ENABLED 或 DISABLED';
COMMENT ON COLUMN organization.department.created_at IS '创建时间';
COMMENT ON COLUMN organization.department.updated_at IS '最后更新时间';

COMMENT ON TABLE organization.department_member IS '全局人员与部门的成员关系';
COMMENT ON COLUMN organization.department_member.id IS '部门成员关系主键 ID';
COMMENT ON COLUMN organization.department_member.department_id IS '关联的部门 ID';
COMMENT ON COLUMN organization.department_member.person_id IS '关联的人员 ID';
COMMENT ON COLUMN organization.department_member.status IS '成员关系状态：ENABLED 或 DISABLED';
COMMENT ON COLUMN organization.department_member.created_at IS '创建时间';
COMMENT ON COLUMN organization.department_member.updated_at IS '最后更新时间';

COMMENT ON TABLE process.node_definition IS '系统支持的节点能力定义及前端配置契约';
COMMENT ON COLUMN process.node_definition.id IS '节点能力定义主键 ID';
COMMENT ON COLUMN process.node_definition.node_type IS '后端执行类型：START、APPROVAL、CONDITION、END，不承担唯一标识作用';
COMMENT ON COLUMN process.node_definition.name IS '节点面板展示名称';
COMMENT ON COLUMN process.node_definition.description IS '节点能力说明';
COMMENT ON COLUMN process.node_definition.icon IS '前端图标标识';
COMMENT ON COLUMN process.node_definition.config_schema_json IS '节点实例允许配置的字段规则，采用 JSON Schema 表述';
COMMENT ON COLUMN process.node_definition.ui_schema_json IS '节点配置面板展示规则';
COMMENT ON COLUMN process.node_definition.status IS '节点定义状态：ENABLED 或 DISABLED';
COMMENT ON COLUMN process.node_definition.created_at IS '创建时间';
COMMENT ON COLUMN process.node_definition.updated_at IS '最后更新时间';

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

COMMENT ON TABLE process.approval_instance IS '一次完整审批申请及其绑定的流程版本';
COMMENT ON COLUMN process.approval_instance.id IS '审批实例 ID';
COMMENT ON COLUMN process.approval_instance.process_id IS '发起时的稳定流程 ID';
COMMENT ON COLUMN process.approval_instance.process_version_id IS '本次运行使用的已发布版本 ID';
COMMENT ON COLUMN process.approval_instance.business_key IS '业务系统中的原单据标识';
COMMENT ON COLUMN process.approval_instance.idempotency_key IS '内部幂等键，全局唯一，重复发起返回同一实例';
COMMENT ON COLUMN process.approval_instance.request_digest IS '发起请求内容的规范化摘要，重放时用于识别内容是否变化';
COMMENT ON COLUMN process.approval_instance.title IS '审批单标题';
COMMENT ON COLUMN process.approval_instance.applicant_person_id IS '发起人员 ID，不建立跨 Schema 外键';
COMMENT ON COLUMN process.approval_instance.applicant_snapshot_json IS '发起时的人员展示信息';
COMMENT ON COLUMN process.approval_instance.approval_form_json IS '给审批人查看的审批单数据快照';
COMMENT ON COLUMN process.approval_instance.execution_payload_json IS '审批通过后调用业务系统使用的参数';
COMMENT ON COLUMN process.approval_instance.action_code IS '后续业务动作标识，为空表示不触发业务执行';
COMMENT ON COLUMN process.approval_instance.status IS '实例状态：RUNNING、APPROVED、REJECTED、CANCELLED 或 ERROR';
COMMENT ON COLUMN process.approval_instance.current_node_execution_id IS '当前活动节点执行记录 ID，结束后置空';
COMMENT ON COLUMN process.approval_instance.started_at IS '审批发起时间';
COMMENT ON COLUMN process.approval_instance.finished_at IS '审批结束时间，运行中为空';
COMMENT ON COLUMN process.approval_instance.created_at IS '创建时间';
COMMENT ON COLUMN process.approval_instance.updated_at IS '最后更新时间';

COMMENT ON TABLE process.approval_node_execution IS '审批实例实际进入过的节点及实际执行路径';
COMMENT ON COLUMN process.approval_node_execution.id IS '节点执行记录 ID';
COMMENT ON COLUMN process.approval_node_execution.instance_id IS '所属审批实例 ID';
COMMENT ON COLUMN process.approval_node_execution.process_version_id IS '对应流程版本 ID';
COMMENT ON COLUMN process.approval_node_execution.node_id IS '版本节点 ID';
COMMENT ON COLUMN process.approval_node_execution.node_type IS '进入节点时固化的执行类型';
COMMENT ON COLUMN process.approval_node_execution.node_name IS '进入节点时固化的节点名称';
COMMENT ON COLUMN process.approval_node_execution.sequence_no IS '实际执行顺序，从 1 开始';
COMMENT ON COLUMN process.approval_node_execution.status IS '节点执行状态：ACTIVE、COMPLETED、REJECTED、CANCELLED 或 ERROR';
COMMENT ON COLUMN process.approval_node_execution.entered_at IS '进入节点时间';
COMMENT ON COLUMN process.approval_node_execution.completed_at IS '离开节点时间，活动节点为空';
COMMENT ON COLUMN process.approval_node_execution.next_node_id IS '实际选择的后续节点 ID';
COMMENT ON COLUMN process.approval_node_execution.result_json IS '节点结果和条件命中信息等扩展数据';
COMMENT ON COLUMN process.approval_node_execution.created_at IS '创建时间';
COMMENT ON COLUMN process.approval_node_execution.updated_at IS '最后更新时间';

COMMENT ON TABLE process.approval_task IS '人工审批节点为每位审批人创建的待办任务';
COMMENT ON COLUMN process.approval_task.id IS '审批任务 ID';
COMMENT ON COLUMN process.approval_task.instance_id IS '所属审批实例 ID';
COMMENT ON COLUMN process.approval_task.node_execution_id IS '所属节点执行记录 ID';
COMMENT ON COLUMN process.approval_task.approver_person_id IS '审批人 ID，不建立跨 Schema 外键';
COMMENT ON COLUMN process.approval_task.approver_snapshot_json IS '审批人当时的姓名等展示信息';
COMMENT ON COLUMN process.approval_task.status IS '任务状态：PENDING、APPROVED、REJECTED 或 CANCELLED';
COMMENT ON COLUMN process.approval_task.created_at IS '待办产生时间';
COMMENT ON COLUMN process.approval_task.handled_at IS '审批完成时间';
COMMENT ON COLUMN process.approval_task.cancelled_at IS '被系统取消时间';
COMMENT ON COLUMN process.approval_task.updated_at IS '最后更新时间';

COMMENT ON TABLE process.approval_record IS '审批人的实际操作，不可修改的审计记录';
COMMENT ON COLUMN process.approval_record.id IS '审批记录 ID';
COMMENT ON COLUMN process.approval_record.instance_id IS '所属审批实例 ID';
COMMENT ON COLUMN process.approval_record.node_execution_id IS '所属节点执行记录 ID';
COMMENT ON COLUMN process.approval_record.task_id IS '对应审批任务 ID，一个任务只允许一条记录';
COMMENT ON COLUMN process.approval_record.operator_person_id IS '实际操作人员 ID';
COMMENT ON COLUMN process.approval_record.operator_snapshot_json IS '操作人员展示信息';
COMMENT ON COLUMN process.approval_record.action IS '操作动作：APPROVE 或 REJECT';
COMMENT ON COLUMN process.approval_record.comment IS '审批意见';
COMMENT ON COLUMN process.approval_record.created_at IS '操作时间';

COMMENT ON TABLE process.business_execution_record IS '审批最终通过后的唯一一次业务系统调用及其结果，同时表示待执行任务';
COMMENT ON COLUMN process.business_execution_record.id IS '执行记录 ID，同时作为稳定的执行标识';
COMMENT ON COLUMN process.business_execution_record.approval_instance_id IS '审批实例 ID，全局唯一，同一个实例最多一条执行记录';
COMMENT ON COLUMN process.business_execution_record.business_action_id IS '实际使用的 integration.business_action ID 快照，不建立跨 Schema 外键';
COMMENT ON COLUMN process.business_execution_record.action_code IS '业务动作标识快照';
COMMENT ON COLUMN process.business_execution_record.request_url IS '实际请求地址快照，由租户回调基础地址和相对路径拼接，取得租户配置后补齐';
COMMENT ON COLUMN process.business_execution_record.http_method IS '实际 HTTP 方法快照，业务动作配置缺失时为空';
COMMENT ON COLUMN process.business_execution_record.relative_path IS '业务动作相对路径快照，业务动作配置缺失时为空';
COMMENT ON COLUMN process.business_execution_record.success_status_codes_json IS '成功状态码规则快照，空数组表示全部 2xx 视为成功';
COMMENT ON COLUMN process.business_execution_record.timeout_ms IS '单次调用超时时间快照，单位为毫秒';
COMMENT ON COLUMN process.business_execution_record.request_payload_json IS '实际发送参数快照，取自审批实例的 execution_payload_json';
COMMENT ON COLUMN process.business_execution_record.status IS '执行状态：PENDING、RUNNING、SUCCEEDED 或 FAILED';
COMMENT ON COLUMN process.business_execution_record.http_status_code IS 'HTTP 响应状态码，未取得响应时为空';
COMMENT ON COLUMN process.business_execution_record.response_body IS '响应内容，保存时按固定上限截断，不包含认证请求头';
COMMENT ON COLUMN process.business_execution_record.error_message IS '网络异常、超时或配置错误摘要，不包含 Service Token';
COMMENT ON COLUMN process.business_execution_record.started_at IS '实际调用开始时间，耗时通过它与结束时间相减计算';
COMMENT ON COLUMN process.business_execution_record.finished_at IS '实际调用结束时间';
COMMENT ON COLUMN process.business_execution_record.created_at IS '创建时间';
COMMENT ON COLUMN process.business_execution_record.updated_at IS '最后更新时间';

COMMENT ON TABLE integration.business_action IS '审批通过后可以执行的一类业务动作及其参数规则';
COMMENT ON COLUMN integration.business_action.id IS '业务动作主键 ID';
COMMENT ON COLUMN integration.business_action.action_code IS '全局唯一、稳定的业务动作标识，由业务系统在发起审批时传入';
COMMENT ON COLUMN integration.business_action.name IS '业务动作展示名称';
COMMENT ON COLUMN integration.business_action.description IS '业务动作说明';
COMMENT ON COLUMN integration.business_action.http_method IS '调用业务系统使用的 HTTP 方法：POST、PUT 或 PATCH';
COMMENT ON COLUMN integration.business_action.relative_path IS '相对于租户 callback_base_url 的路径，必须以 / 开头且不能是完整 URL';
COMMENT ON COLUMN integration.business_action.request_schema_json IS 'execution_payload 的 JSON Schema，根类型必须是 object';
COMMENT ON COLUMN integration.business_action.success_status_codes_json IS '视为调用成功的 HTTP 状态码数组，为空数组表示全部 2xx';
COMMENT ON COLUMN integration.business_action.timeout_ms IS '单次调用业务系统的超时时间，单位毫秒';
COMMENT ON COLUMN integration.business_action.status IS '业务动作状态：ENABLED 或 DISABLED，停用后不能用于新申请';
COMMENT ON COLUMN integration.business_action.created_at IS '创建时间';
COMMENT ON COLUMN integration.business_action.updated_at IS '最后更新时间';
