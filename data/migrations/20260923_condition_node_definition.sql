-- 为已经初始化过的数据库补上"条件分支"节点定义。
--
-- 背景：init.sql 的种子数据使用 ON CONFLICT (id) DO NOTHING，所以给 init.sql 追加
-- 新的种子条目对已经执行过初始化脚本的库不生效，需要单独执行本脚本。
--
-- 全新库不需要执行本脚本：init.sql 已经包含这条定义。
-- 脚本幂等，重复执行不会产生重复数据。

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

-- 列注释同步更新，说明现在支持四种执行类型。
COMMENT ON COLUMN process.node_definition.node_type IS '后端执行类型：START、APPROVAL、CONDITION、END，不承担唯一标识作用';
