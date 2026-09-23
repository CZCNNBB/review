-- 结束节点去掉「结束状态」配置：走到结束节点就是审批通过、流程完成。
--
-- 背景：审批通过还是不通过由审批人决定。人工审批被拒绝时实例当场结束（见
-- ApprovalEngine.reject_instance），根本走不到结束节点，所以结束节点上的
-- result_status 只能表达"系统自动驳回"这一种边缘情况，容易让配置的人误以为
-- 流程的结果是在这里决定的。
--
-- 修改内容：把 END 种子定义的 config_schema_json 清空、description 改写。
-- 全新库不需要执行本脚本：init.sql 已经是清理后的内容。
-- 脚本幂等，重复执行结果一致。

UPDATE process.node_definition
SET description = '流程正常的最终出口，走到这里就是审批通过、流程完成，节点本身没有配置项。审批被拒绝时实例在人工审批节点当场结束，不会走到结束节点。',
    config_schema_json = '{
        "type": "object",
        "title": "结束",
        "additionalProperties": false,
        "properties": {}
    }'::jsonb,
    ui_schema_json = '{"ui:order": []}'::jsonb,
    updated_at = NOW()
WHERE id = '00000000-0000-0000-0000-000000000103'
  AND node_type = 'END';
