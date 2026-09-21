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

CREATE TABLE IF NOT EXISTS tenant.tenant_callback_credential (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name VARCHAR(100) NOT NULL,
    key_id VARCHAR(64) NOT NULL,
    secret_ciphertext TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    CONSTRAINT fk_tenant_callback_credential_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenant.tenant (id)
);

CREATE INDEX IF NOT EXISTS ix_tenant_tenant_callback_credential_tenant_id
    ON tenant.tenant_callback_credential (tenant_id);

CREATE UNIQUE INDEX IF NOT EXISTS ix_tenant_tenant_callback_credential_key_id
    ON tenant.tenant_callback_credential (key_id);

CREATE INDEX IF NOT EXISTS ix_tenant_tenant_callback_credential_status
    ON tenant.tenant_callback_credential (status);

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
        '流程结束节点，进入审批通过的结束节点后创建后续业务动作任务',
        'flag',
        '{
            "type": "object",
            "title": "结束",
            "additionalProperties": false,
            "required": ["result_status"],
            "properties": {
                "result_status": {
                    "type": "string",
                    "title": "结束状态",
                    "description": "APPROVED 表示审批通过，REJECTED 表示审批拒绝",
                    "enum": ["APPROVED", "REJECTED"]
                }
            }
        }',
        '{
            "result_status": {"ui:widget": "select"}
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

COMMENT ON TABLE tenant.tenant_callback_credential IS '审批中心回调业务系统时使用的签名凭据';
COMMENT ON COLUMN tenant.tenant_callback_credential.id IS '回调凭据主键 ID';
COMMENT ON COLUMN tenant.tenant_callback_credential.tenant_id IS '所属租户 ID';
COMMENT ON COLUMN tenant.tenant_callback_credential.name IS '回调凭据用途名称';
COMMENT ON COLUMN tenant.tenant_callback_credential.key_id IS '对外标识回调凭据的 Key ID';
COMMENT ON COLUMN tenant.tenant_callback_credential.secret_ciphertext IS '使用应用主密钥加密后的回调签名密钥';
COMMENT ON COLUMN tenant.tenant_callback_credential.status IS '回调凭据状态：ENABLED 或 REVOKED';
COMMENT ON COLUMN tenant.tenant_callback_credential.expires_at IS '过期时间，为空表示长期有效';
COMMENT ON COLUMN tenant.tenant_callback_credential.created_at IS '创建时间';
COMMENT ON COLUMN tenant.tenant_callback_credential.revoked_at IS '撤销时间';
COMMENT ON COLUMN tenant.tenant_callback_credential.created_by IS '创建操作人 ID，初期允许为空';

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
COMMENT ON COLUMN process.node_definition.node_type IS '后端执行类型：START、APPROVAL、END，不承担唯一标识作用';
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
