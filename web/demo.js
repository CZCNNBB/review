/* ==========================================================================
   示例数据（仅用于界面预览，不连接后端）
   作用：在浏览器里拦截 fetch，返回一组固定的假数据，方便在没有后端的环境里
        完整点一遍页面。默认关闭，只有点击“用示例数据预览”或地址栏加 ?demo=1
        才会启用。
   说明：写操作不会真正保存，只返回成功响应并提示当前处于示例模式。
        正式联调前可以直接删除本文件和 index.html 里的脚本引用。
   ========================================================================== */

(function () {
  'use strict';

  const TENANT_ID = '10000000-0000-4000-8000-000000000001';
  const PERSON_ZHANG = '20000000-0000-4000-8000-000000000001';
  const PERSON_LI = '20000000-0000-4000-8000-000000000002';
  const PERSON_WANG = '20000000-0000-4000-8000-000000000003';
  const PERSON_ZHAO = '20000000-0000-4000-8000-000000000004';
  const DEPARTMENT_ID = '30000000-0000-4000-8000-000000000001';
  const PROCESS_ID = '40000000-0000-4000-8000-000000000001';
  const VERSION_V1 = '41000000-0000-4000-8000-000000000001';
  const VERSION_V2 = '41000000-0000-4000-8000-000000000002';
  const VERSION_V3 = '41000000-0000-4000-8000-000000000003';
  const NODE_START = '50000000-0000-4000-8000-000000000001';
  const NODE_FINANCE = '50000000-0000-4000-8000-000000000002';
  const NODE_BOSS = '50000000-0000-4000-8000-000000000003';
  const NODE_APPROVED = '50000000-0000-4000-8000-000000000004';
  const NODE_BRANCH = '50000000-0000-4000-8000-000000000006';
  const ACTION_ID = '60000000-0000-4000-8000-000000000001';
  const INSTANCE_RUNNING = '70000000-0000-4000-8000-000000000001';
  const INSTANCE_DONE = '70000000-0000-4000-8000-000000000002';
  const TASK_FINANCE_A = '80000000-0000-4000-8000-000000000001';
  const TASK_FINANCE_B = '80000000-0000-4000-8000-000000000002';
  const TASK_DONE = '80000000-0000-4000-8000-000000000003';
  const EXECUTION_OK = '90000000-0000-4000-8000-000000000001';
  const EXECUTION_FAIL = '90000000-0000-4000-8000-000000000002';

  const NODE_DEF_START = '00000000-0000-0000-0000-000000000101';
  const NODE_DEF_APPROVAL = '00000000-0000-0000-0000-000000000102';
  const NODE_DEF_END = '00000000-0000-0000-0000-000000000103';
  const NODE_DEF_CONDITION = '00000000-0000-0000-0000-000000000104';

  const now = Date.now();
  const at = (minutesAgo) => new Date(now - minutesAgo * 60000).toISOString();

  const state = {
    // 默认带一版草稿，方便直接进画布拖拽体验编排。
    draftVersionId: VERSION_V3,
    runningInstanceApproved: false,
  };

  const tenants = [
    {
      id: TENANT_ID,
      code: 'PAYMENT',
      name: '付款系统',
      description: '负责供应商付款和报销单的业务系统',
      callback_base_url: 'https://payment.example.com',
      status: 'ENABLED',
      created_at: at(60 * 24 * 12),
      updated_at: at(60 * 24),
    },
    {
      id: '10000000-0000-4000-8000-000000000002',
      code: 'PURCHASE',
      name: '采购系统',
      description: '采购申请与合同评审',
      callback_base_url: 'https://purchase.example.com',
      status: 'ENABLED',
      created_at: at(60 * 24 * 9),
      updated_at: at(60 * 30),
    },
  ];

  const persons = [
    { id: PERSON_ZHANG, name: '张伟', mobile: '13800000001', email: 'zhangwei@example.com', status: 'ENABLED', created_at: at(60 * 24 * 10), updated_at: at(60 * 24 * 10) },
    { id: PERSON_LI, name: '李娜', mobile: '13800000002', email: 'lina@example.com', status: 'ENABLED', created_at: at(60 * 24 * 10), updated_at: at(60 * 24 * 10) },
    { id: PERSON_WANG, name: '王强', mobile: '13800000003', email: 'wangqiang@example.com', status: 'ENABLED', created_at: at(60 * 24 * 8), updated_at: at(60 * 24 * 8) },
    { id: PERSON_ZHAO, name: '赵敏', mobile: '13800000004', email: 'zhaomin@example.com', status: 'ENABLED', created_at: at(60 * 24 * 8), updated_at: at(60 * 24 * 8) },
  ];

  const departments = [
    { id: DEPARTMENT_ID, code: 'FINANCE', name: '财务部', status: 'ENABLED', created_at: at(60 * 24 * 10), updated_at: at(60 * 24 * 10) },
    { id: '30000000-0000-4000-8000-000000000002', code: 'GENERAL', name: '总经办', status: 'ENABLED', created_at: at(60 * 24 * 10), updated_at: at(60 * 24 * 10) },
  ];

  const departmentMembers = [
    { id: '31000000-0000-4000-8000-000000000001', department_id: DEPARTMENT_ID, department_name: '财务部', person_id: PERSON_ZHANG, person_name: '张伟', status: 'ENABLED', created_at: at(60 * 24 * 9), updated_at: at(60 * 24 * 9) },
    { id: '31000000-0000-4000-8000-000000000002', department_id: DEPARTMENT_ID, department_name: '财务部', person_id: PERSON_ZHAO, person_name: '赵敏', status: 'ENABLED', created_at: at(60 * 24 * 9), updated_at: at(60 * 24 * 9) },
  ];

  const bindings = [
    { binding_id: '32000000-0000-4000-8000-000000000001', tenant_id: TENANT_ID, person_id: PERSON_ZHANG, person_name: '张伟', employee_no: 'F0001', external_user_id: 'u_1001', display_name: '张伟（财务）', status: 'ENABLED', created_at: at(60 * 24 * 9), updated_at: at(60 * 24 * 9) },
    { binding_id: '32000000-0000-4000-8000-000000000002', tenant_id: TENANT_ID, person_id: PERSON_LI, person_name: '李娜', employee_no: 'M0001', external_user_id: 'u_2001', display_name: '李娜（总经理）', status: 'ENABLED', created_at: at(60 * 24 * 9), updated_at: at(60 * 24 * 9) },
  ];

  const processes = [
    {
      id: PROCESS_ID,
      name: '付款审批流程',
      description: '金额超过 1 万元的付款申请需要总经理审批，其余由财务审批后直接通过。',
      status: 'ENABLED',
      current_version_id: VERSION_V2,
      current_version_no: 2,
      draft_version_id: null,
      draft_version_no: null,
      node_count: 6,
      created_at: at(60 * 24 * 8),
      updated_at: at(60 * 24 * 2),
    },
    {
      id: '40000000-0000-4000-8000-000000000002',
      name: '采购申请流程',
      description: '采购申请的两级审批。',
      status: 'DRAFT',
      current_version_id: null,
      current_version_no: null,
      draft_version_id: '41000000-0000-4000-8000-000000000011',
      draft_version_no: 1,
      node_count: 2,
      created_at: at(60 * 24 * 3),
      updated_at: at(60 * 24 * 3),
    },
  ];

  const versions = [
    { id: VERSION_V1, process_id: PROCESS_ID, version_no: 1, status: 'PUBLISHED', name: '付款审批流程', description: null, revision: 3, node_count: 3, created_at: at(60 * 24 * 8), updated_at: at(60 * 24 * 8), published_at: at(60 * 24 * 8) },
    { id: VERSION_V2, process_id: PROCESS_ID, version_no: 2, status: 'PUBLISHED', name: '付款审批流程', description: null, revision: 6, node_count: 6, created_at: at(60 * 24 * 4), updated_at: at(60 * 24 * 2), published_at: at(60 * 24 * 2) },
  ];

  const graphNodes = [
    { id: NODE_START, node_definition_id: NODE_DEF_START, node_type: 'START', node_definition_name: '开始', name: '开始', config: {}, position: { x: 80, y: 180 } },
    {
      id: NODE_FINANCE,
      node_definition_id: NODE_DEF_APPROVAL,
      node_type: 'APPROVAL',
      node_definition_name: '人工审批',
      name: '财务审批',
      config: { approval_mode: 'AND', approvers: [{ person_id: PERSON_ZHANG }, { person_id: PERSON_ZHAO }] },
      position: { x: 300, y: 180 },
    },
    {
      id: NODE_BRANCH,
      node_definition_id: NODE_DEF_CONDITION,
      node_type: 'CONDITION',
      node_definition_name: '条件分支',
      name: '按金额分流',
      config: {},
      position: { x: 520, y: 150 },
    },
    {
      id: NODE_BOSS,
      node_definition_id: NODE_DEF_APPROVAL,
      node_type: 'APPROVAL',
      node_definition_name: '人工审批',
      name: '总经理审批',
      config: { approval_mode: 'OR', approvers: [{ person_id: PERSON_LI }] },
      position: { x: 800, y: 70 },
    },
    { id: NODE_APPROVED, node_definition_id: NODE_DEF_END, node_type: 'END', node_definition_name: '结束', name: '审批通过', config: {}, position: { x: 1080, y: 150 } },
  ];

  // 分流集中在条件分支节点里：前面每条带条件，最后一条是"其余情况"。
  // 结束节点只有一个含义：走到它 = 审批通过、流程完成。审批被拒绝时实例在人工审批
  // 节点当场结束，不经过结束节点，所以图上没有"拒绝出口"。
  const connections = [
    { source_node_id: NODE_START, target_node_id: NODE_FINANCE },
    { source_node_id: NODE_FINANCE, target_node_id: NODE_BRANCH },
    { source_node_id: NODE_BRANCH, target_node_id: NODE_BOSS, condition: { field: 'approval_form.amount', operator: 'GT', value: 10000 } },
    { source_node_id: NODE_BRANCH, target_node_id: NODE_APPROVED },
    { source_node_id: NODE_BOSS, target_node_id: NODE_APPROVED },
  ];

  const formSchema = {
    type: 'object',
    title: '付款申请',
    required: ['amount', 'supplier_name'],
    additionalProperties: false,
    properties: {
      amount: { type: 'number', title: '付款金额', minimum: 0 },
      supplier_name: { type: 'string', title: '供应商名称' },
      pay_date: { type: 'string', format: 'date', title: '期望付款日期' },
      remark: { type: 'string', title: '备注' },
    },
  };

  // 与 data/init.sql 里的种子定义保持一致，保证示例模式和真实库的配置表单一致。
  const nodeDefinitions = [
    {
      id: NODE_DEF_START,
      node_type: 'START',
      name: '开始',
      description: '流程入口节点，每条流程必须且只能有一个开始节点',
      icon: 'play-circle',
      config_schema_json: { type: 'object', title: '开始', additionalProperties: false, properties: {} },
      ui_schema_json: { 'ui:order': [] },
      status: 'ENABLED',
      created_at: at(60 * 24 * 30),
      updated_at: at(60 * 24 * 30),
    },
    {
      id: NODE_DEF_APPROVAL,
      node_type: 'APPROVAL',
      name: '人工审批',
      description: '人工审批节点，配置审批模式和审批人，进入节点时同时为全部审批人创建待办任务',
      icon: 'user-check',
      config_schema_json: {
        type: 'object',
        title: '人工审批',
        additionalProperties: false,
        required: ['approval_mode', 'approvers'],
        properties: {
          approval_mode: {
            type: 'string',
            title: '审批模式',
            description: 'AND 表示所有人同意后通过，OR 表示任意一人同意即通过',
            enum: ['AND', 'OR'],
          },
          approvers: {
            type: 'array',
            title: '审批人',
            minItems: 1,
            items: {
              type: 'object',
              additionalProperties: false,
              required: ['person_id'],
              properties: {
                person_id: { type: 'string', format: 'uuid', title: '人员 ID' },
              },
            },
          },
        },
      },
      ui_schema_json: {
        approval_mode: { 'ui:widget': 'select' },
        approvers: { 'ui:widget': 'person-select' },
      },
      status: 'ENABLED',
      created_at: at(60 * 24 * 30),
      updated_at: at(60 * 24 * 30),
    },
    {
      id: NODE_DEF_CONDITION,
      node_type: 'CONDITION',
      name: '条件分支',
      description: '按审批表单里的字段判断走哪条路，本身不产生审批任务。分支条件和去向在节点的分支编辑器里配置，进入后立即选路。',
      icon: 'git-branch',
      config_schema_json: { type: 'object', title: '条件分支', additionalProperties: false, properties: {} },
      ui_schema_json: { 'ui:order': [] },
      status: 'ENABLED',
      created_at: at(60 * 24 * 30),
      updated_at: at(60 * 24 * 30),
    },
    {
      id: NODE_DEF_END,
      node_type: 'END',
      name: '结束',
      description: '流程正常的最终出口，走到这里就是审批通过、流程完成，节点本身没有配置项。审批被拒绝时实例在人工审批节点当场结束，不会走到结束节点。',
      icon: 'flag',
      config_schema_json: {
        type: 'object',
        title: '结束',
        additionalProperties: false,
        properties: {},
      },
      ui_schema_json: { 'ui:order': [] },
      status: 'ENABLED',
      created_at: at(60 * 24 * 30),
      updated_at: at(60 * 24 * 30),
    },
  ];

  const businessActions = [
    {
      id: ACTION_ID,
      action_code: 'PAYMENT_EXECUTE',
      name: '执行付款',
      description: '审批通过后调用付款系统执行付款',
      http_method: 'POST',
      relative_path: '/payments/execute',
      request_schema: {
        type: 'object',
        required: ['payment_id', 'amount'],
        properties: { payment_id: { type: 'string' }, amount: { type: 'number', exclusiveMinimum: 0 } },
        additionalProperties: false,
      },
      success_status_codes: [200, 201],
      timeout_ms: 5000,
      status: 'ENABLED',
      created_at: at(60 * 24 * 7),
      updated_at: at(60 * 24 * 7),
    },
    {
      id: '60000000-0000-4000-8000-000000000002',
      action_code: 'PAYMENT_CANCEL',
      name: '撤销付款',
      description: '审批被拒绝时通知付款系统释放额度',
      http_method: 'POST',
      relative_path: '/payments/cancel',
      request_schema: { type: 'object', required: ['payment_id'], properties: { payment_id: { type: 'string' } } },
      success_status_codes: [],
      timeout_ms: 3000,
      status: 'DISABLED',
      created_at: at(60 * 24 * 7),
      updated_at: at(60 * 24 * 5),
    },
  ];

  const apiKeys = [
    { id: '11000000-0000-4000-8000-000000000001', tenant_id: TENANT_ID, name: '付款系统生产环境', api_key: 'appr_live_7f3c9d21ab4e', status: 'ENABLED', expires_at: null, last_used_at: at(12), created_at: at(60 * 24 * 9), revoked_at: null },
    { id: '11000000-0000-4000-8000-000000000002', tenant_id: TENANT_ID, name: '付款系统测试环境', api_key: 'appr_test_1a2b3c4d5e6f', status: 'ENABLED', expires_at: at(-60 * 24 * 90), last_used_at: at(60 * 26), created_at: at(60 * 24 * 9), revoked_at: null },
  ];

  const credentials = [
    { id: '12000000-0000-4000-8000-000000000001', tenant_id: TENANT_ID, name: '审批中心服务账号', header_name: 'Authorization', token_prefix: 'Bearer', status: 'ENABLED', expires_at: null, created_at: at(60 * 24 * 8), revoked_at: null },
  ];

  const processBindings = [
    { id: '13000000-0000-4000-8000-000000000001', tenant_id: TENANT_ID, process_id: PROCESS_ID, status: 'ENABLED', created_at: at(60 * 24 * 8), updated_at: at(60 * 24 * 8) },
  ];

  const actionBindings = [
    { id: '14000000-0000-4000-8000-000000000001', tenant_id: TENANT_ID, business_action_id: ACTION_ID, status: 'ENABLED', created_at: at(60 * 24 * 7), updated_at: at(60 * 24 * 7) },
  ];

  const instanceRunning = {
    id: INSTANCE_RUNNING,
    process_id: PROCESS_ID,
    process_name: '付款审批流程',
    process_version_id: VERSION_V2,
    process_version_no: 2,
    business_key: 'PAY-20260923-001',
    title: '供应商付款申请',
    applicant_person_id: PERSON_WANG,
    applicant_snapshot: { name: '王强' },
    action_code: 'PAYMENT_EXECUTE',
    status: 'RUNNING',
    approval_form: { amount: 26000, supplier_name: '宁波精工材料有限公司', pay_date: '2026-09-30', remark: '9 月账期付款' },
    current_node: null,
    node_executions: [],
    tasks: [],
    records: [],
    pending_tasks: [],
    started_at: at(95),
    finished_at: null,
    duration_ms: 95 * 60000,
    created_at: at(95),
    updated_at: at(95),
  };

  const instanceDone = {
    id: INSTANCE_DONE,
    process_id: PROCESS_ID,
    process_name: '付款审批流程',
    process_version_id: VERSION_V2,
    process_version_no: 2,
    business_key: 'PAY-20260922-004',
    title: '供应商付款申请（已通过）',
    applicant_person_id: PERSON_WANG,
    applicant_snapshot: { name: '王强' },
    action_code: 'PAYMENT_EXECUTE',
    status: 'APPROVED',
    approval_form: { amount: 8600, supplier_name: '苏州恒信包装有限公司', pay_date: '2026-09-25' },
    current_node: null,
    node_executions: [],
    tasks: [],
    records: [],
    pending_tasks: [],
    started_at: at(60 * 20),
    finished_at: at(60 * 18),
    duration_ms: 2 * 60 * 60000,
    created_at: at(60 * 20),
    updated_at: at(60 * 18),
  };

  const tasksRunning = [
    { id: TASK_FINANCE_A, instance_id: INSTANCE_RUNNING, node_execution_id: 'a1000000-0000-4000-8000-000000000002', instance_title: '供应商付款申请', business_key: 'PAY-20260923-001', node_name: '财务审批', approver_person_id: PERSON_ZHANG, approver_snapshot: { name: '张伟' }, status: 'PENDING', created_at: at(95), handled_at: null, cancelled_at: null, duration_ms: 95 * 60000 },
    { id: TASK_FINANCE_B, instance_id: INSTANCE_RUNNING, node_execution_id: 'a1000000-0000-4000-8000-000000000002', instance_title: '供应商付款申请', business_key: 'PAY-20260923-001', node_name: '财务审批', approver_person_id: PERSON_ZHAO, approver_snapshot: { name: '赵敏' }, status: 'PENDING', created_at: at(95), handled_at: null, cancelled_at: null, duration_ms: 95 * 60000 },
  ];

  const taskDone = { id: TASK_DONE, instance_id: INSTANCE_DONE, node_execution_id: 'a1000000-0000-4000-8000-000000000012', instance_title: '供应商付款申请（已通过）', business_key: 'PAY-20260922-004', node_name: '财务审批', approver_person_id: PERSON_ZHANG, approver_snapshot: { name: '张伟' }, status: 'APPROVED', created_at: at(60 * 20), handled_at: at(60 * 19), cancelled_at: null, duration_ms: 60 * 60000 };

  function nodeExecution(id, nodeId, nodeType, name, sequence, status, enteredAgo, completedAgo, extra) {
    return Object.assign(
      {
        id,
        node_id: nodeId,
        node_type: nodeType,
        node_name: name,
        sequence_no: sequence,
        status,
        entered_at: at(enteredAgo),
        completed_at: completedAgo === null ? null : at(completedAgo),
        duration_ms: completedAgo === null ? (enteredAgo * 60000) : ((enteredAgo - completedAgo) * 60000),
        next_node_id: null,
        next_node_name: null,
        condition_hit: null,
        result: {},
      },
      extra || {}
    );
  }

  function buildTimeline(instance) {
    if (instance.id === INSTANCE_RUNNING) {
      const entries = [
        {
          node_execution: nodeExecution('a1000000-0000-4000-8000-000000000001', NODE_START, 'START', '开始', 1, 'COMPLETED', 95, 95, { next_node_id: NODE_FINANCE, next_node_name: '财务审批' }),
          tasks: [],
          records: [],
        },
        {
          node_execution: nodeExecution('a1000000-0000-4000-8000-000000000002', NODE_FINANCE, 'APPROVAL', '财务审批', 2, 'ACTIVE', 95, null),
          tasks: tasksRunning,
          records: [],
        },
      ];
      return {
        instance_id: INSTANCE_RUNNING,
        title: instanceRunning.title,
        status: 'RUNNING',
        started_at: instanceRunning.started_at,
        finished_at: null,
        duration_ms: 95 * 60000,
        entries,
      };
    }

    const recordA = { id: 'b1000000-0000-4000-8000-000000000001', instance_id: INSTANCE_DONE, node_execution_id: 'a1000000-0000-4000-8000-000000000012', task_id: TASK_DONE, operator_person_id: PERSON_ZHANG, operator_snapshot: { name: '张伟' }, action: 'APPROVE', comment: '发票与合同一致，同意付款。', created_at: at(60 * 19), duration_ms: 60 * 60000 };
    const recordB = { id: 'b1000000-0000-4000-8000-000000000002', instance_id: INSTANCE_DONE, node_execution_id: 'a1000000-0000-4000-8000-000000000012', task_id: '80000000-0000-4000-8000-000000000004', operator_person_id: PERSON_ZHAO, operator_snapshot: { name: '赵敏' }, action: 'APPROVE', comment: '同意。', created_at: at(60 * 19), duration_ms: 60 * 60000 };

    const entries = [
      {
        node_execution: nodeExecution('a1000000-0000-4000-8000-000000000011', NODE_START, 'START', '开始', 1, 'COMPLETED', 60 * 20, 60 * 20, { next_node_id: NODE_FINANCE, next_node_name: '财务审批' }),
        tasks: [],
        records: [],
      },
      {
        node_execution: nodeExecution('a1000000-0000-4000-8000-000000000012', NODE_FINANCE, 'APPROVAL', '财务审批', 2, 'COMPLETED', 60 * 20, 60 * 19, { next_node_id: NODE_APPROVED, next_node_name: '审批通过', condition_hit: false, result: { condition_hit: false } }),
        tasks: [Object.assign({}, taskDone), Object.assign({}, taskDone, { id: '80000000-0000-4000-8000-000000000004', approver_person_id: PERSON_ZHAO, approver_snapshot: { name: '赵敏' } })],
        records: [recordA, recordB],
      },
      {
        node_execution: nodeExecution('a1000000-0000-4000-8000-000000000013', NODE_APPROVED, 'END', '审批通过', 3, 'COMPLETED', 60 * 19, 60 * 19),
        tasks: [],
        records: [],
      },
    ];

    return {
      instance_id: INSTANCE_DONE,
      title: instanceDone.title,
      status: 'APPROVED',
      started_at: instanceDone.started_at,
      finished_at: instanceDone.finished_at,
      duration_ms: instanceDone.duration_ms,
      entries,
    };
  }

  function buildInstanceDetail(instance) {
    const timeline = buildTimeline(instance);
    const nodeExecutions = timeline.entries.map((entry) => entry.node_execution);
    const tasks = timeline.entries.flatMap((entry) => entry.tasks);
    const records = timeline.entries.flatMap((entry) => entry.records);
    const current = nodeExecutions.find((node) => node.status === 'ACTIVE') || null;
    return Object.assign({}, instance, {
      node_executions: nodeExecutions,
      tasks,
      records,
      current_node: current,
      pending_tasks: tasks.filter((task) => task.status === 'PENDING'),
    });
  }

  const executionRecords = [
    { id: EXECUTION_OK, approval_instance_id: INSTANCE_DONE, action_code: 'PAYMENT_EXECUTE', http_method: 'POST', relative_path: '/payments/execute', status: 'SUCCEEDED', http_status_code: 200, error_message: null, started_at: at(60 * 18), finished_at: at(60 * 18 - 1), duration_ms: 412, created_at: at(60 * 18) },
    { id: EXECUTION_FAIL, approval_instance_id: '70000000-0000-4000-8000-000000000003', action_code: 'PAYMENT_EXECUTE', http_method: 'POST', relative_path: '/payments/execute', status: 'FAILED', http_status_code: 502, error_message: '业务系统返回 502，超过成功状态码范围（200、201）', started_at: at(60 * 30), finished_at: at(60 * 30 - 1), duration_ms: 5000, created_at: at(60 * 30) },
  ];

  const usageRecords = [
    { id: '15000000-0000-4000-8000-000000000001', tenant_id: TENANT_ID, process_id: PROCESS_ID, process_version_id: VERSION_V2, approval_instance_id: INSTANCE_RUNNING, business_key: 'PAY-20260923-001', action_code: 'PAYMENT_EXECUTE', created_at: at(95), approval_status: 'RUNNING', approval_title: '供应商付款申请', current_node_name: '财务审批', started_at: at(95), finished_at: null, duration_ms: 95 * 60000 },
    { id: '15000000-0000-4000-8000-000000000002', tenant_id: TENANT_ID, process_id: PROCESS_ID, process_version_id: VERSION_V2, approval_instance_id: INSTANCE_DONE, business_key: 'PAY-20260922-004', action_code: 'PAYMENT_EXECUTE', created_at: at(60 * 20), approval_status: 'APPROVED', approval_title: '供应商付款申请（已通过）', current_node_name: null, started_at: at(60 * 20), finished_at: at(60 * 18), duration_ms: 2 * 60 * 60000 },
  ];

  /* ---------------------------------------------------------------------
     请求匹配
     --------------------------------------------------------------------- */

  function graphResponse(versionId) {
    const version = versions.find((item) => item.id === versionId);
    const isDraft = versionId === state.draftVersionId;
    return {
      process_id: PROCESS_ID,
      version_id: versionId,
      version_no: version ? version.version_no : 3,
      version_status: isDraft ? 'DRAFT' : 'PUBLISHED',
      revision: version ? version.revision : 0,
      name: '付款审批流程',
      description: '金额超过 1 万元的付款申请需要总经理审批。',
      form_schema: formSchema,
      form_ui_schema: {},
      orchestration: { connections },
      nodes: graphNodes.map((node) => Object.assign({}, node, { created_at: at(60 * 24 * 4), updated_at: at(60 * 24 * 2) })),
      created_at: at(60 * 24 * 4),
      updated_at: at(60 * 24 * 2),
      published_at: isDraft ? null : at(60 * 24 * 2),
    };
  }

  function resolve(method, path) {
    const url = path.split('?')[0];
    const query = new URLSearchParams(path.split('?')[1] || '');
    const segments = url.split('/').filter(Boolean);

    if (segments[0] !== 'api') return null;
    const rest = segments.slice(1).join('/');

    if (method === 'GET') {
      if (rest === 'admin/tenants') return tenants;
      if (rest === 'admin/tenants/' + TENANT_ID) return tenants[0];
      if (rest === 'admin/tenants/' + TENANT_ID + '/api-keys') return apiKeys;
      if (rest === 'admin/tenants/' + TENANT_ID + '/callback-credentials') return credentials;
      if (rest === 'admin/tenants/' + TENANT_ID + '/process-bindings') return processBindings;
      if (rest === 'admin/tenants/' + TENANT_ID + '/business-action-bindings') return actionBindings;
      if (rest === 'admin/tenants/' + TENANT_ID + '/process-usage-records') return usageRecords;
      if (rest === 'admin/tenants/' + TENANT_ID + '/persons') return bindings;
      if (rest === 'admin/persons') return persons;
      if (rest === 'admin/departments') return departments;
      if (rest === 'admin/departments/' + DEPARTMENT_ID + '/members') return departmentMembers;
      if (rest === 'admin/node-definitions') return nodeDefinitions;
      if (rest === 'admin/processes') return processes.map(withVersionSummary);
      if (rest === 'admin/processes/' + PROCESS_ID) return withVersionSummary(processes[0]);
      if (rest === 'admin/processes/' + PROCESS_ID + '/versions') return versions.slice().reverse();
      if (rest === 'admin/business-actions') return businessActions;
      if (rest === 'admin/execution-records') return executionRecords;
      if (rest === 'tenant/context') return { tenant_id: TENANT_ID, tenant_code: 'PAYMENT', tenant_name: '付款系统', api_key_id: apiKeys[0].id };

      // 带资源 ID 的接口：/api/<模块>/<资源>[/<资源 ID>][/<子资源>]
      const p1 = segments[1];
      const p2 = segments[2];
      const p3 = segments[3];
      const p4 = segments[4];

      if (p1 === 'admin' && p2 === 'tenants' && p3) {
        if (p4 === 'api-keys') return apiKeys;
        if (p4 === 'callback-credentials') return credentials;
        // 授权只挂在第一个租户上，其余租户返回空列表，避免平铺页面出现重复行。
        if (p4 === 'process-bindings') return p3 === TENANT_ID ? processBindings : [];
        if (p4 === 'business-action-bindings') return p3 === TENANT_ID ? actionBindings : [];
        if (p4 === 'process-usage-records') return usageRecords;
        if (p4 === 'persons') return bindings;
        return tenants[0];
      }
      if (p1 === 'admin' && p2 === 'process-versions' && p4 === 'graph') return graphResponse(p3);
      if (p1 === 'admin' && p2 === 'business-actions' && p3) return businessActions[0];
      if (p1 === 'admin' && p2 === 'execution-records' && p3) return executionDetail(p3);
      if (rest === 'approval-tasks') {
        const wanted = query.getAll('status');
        const personId = query.get('person_id');
        return approvalTasks()
          .filter((task) => !wanted.length || wanted.includes(task.status))
          .filter((task) => !personId || task.approver_person_id === personId);
      }
      if (p1 === 'approval-instances' && p2) {
        const instance = p2 === INSTANCE_DONE ? instanceDone : instanceRunning;
        return p3 === 'timeline' ? buildTimeline(instance) : buildInstanceDetail(instance);
      }
    }

    if (method !== 'GET') return mutate(method, rest, segments);

    return null;
  }

  function withVersionSummary(process) {
    if (process.id !== processes[0].id) return process;
    return Object.assign({}, process, {
      draft_version_id: state.draftVersionId,
      draft_version_no: state.draftVersionId ? 3 : null,
    });
  }

  function approvalTasks() {
    return [].concat(tasksRunning, [taskDone]);
  }

  function executionDetail(recordId) {
    const record = executionRecords.find((item) => item.id === recordId) || executionRecords[0];
    return Object.assign({}, record, {
      business_action_id: ACTION_ID,
      request_url: 'https://payment.example.com/payments/execute',
      timeout_ms: 5000,
      success_status_codes: [200, 201],
      request_payload: { payment_id: 'PAY-20260922-004', amount: 8600 },
      response_body: JSON.stringify({ code: 0, message: 'ok', data: { payment_id: 'PAY-20260922-004', status: 'PAID' } }, null, 2),
      updated_at: record.created_at,
    });
  }

  function mutate(method, rest, segments) {
    const p1 = segments[1];
    const p2 = segments[2];
    const p3 = segments[3];
    const p4 = segments[4];

    if (rest === 'admin/tenants') {
      return Object.assign({}, tenants[0], { id: '10000000-0000-4000-8000-000000000009', code: 'NEWTENANT', name: '新租户' });
    }
    if (p1 === 'admin' && p2 === 'tenants' && p4 === 'api-keys') {
      return Object.assign({}, apiKeys[0], { id: '11000000-0000-4000-8000-000000000009', name: '新签发的密钥', api_key: 'appr_live_demo00000000', last_used_at: null });
    }
    if (p1 === 'admin' && p2 === 'tenants' && p4 === 'callback-credentials') {
      return Object.assign({}, credentials[0], { id: '12000000-0000-4000-8000-000000000009' });
    }
    if (p1 === 'admin' && p2 === 'tenants') return tenants[0];
    if (rest === 'admin/persons') return Object.assign({}, persons[0], { id: '20000000-0000-4000-8000-000000000009', name: '新人员' });
    if (rest === 'admin/departments') return Object.assign({}, departments[0], { id: '30000000-0000-4000-8000-000000000009' });
    if (rest === 'admin/processes') {
      return Object.assign({}, processes[0], { id: '40000000-0000-4000-8000-000000000009', name: '新审批流', current_version_id: null, current_version_no: null, draft_version_id: VERSION_V3, draft_version_no: 1, node_count: 0 });
    }
    if (rest === 'admin/processes/' + PROCESS_ID + '/draft') {
      state.draftVersionId = VERSION_V3;
      return { id: VERSION_V3, process_id: PROCESS_ID, version_no: 3, status: 'DRAFT', name: '付款审批流程', description: null, revision: 0, node_count: graphNodes.length, created_at: at(0), updated_at: at(0), published_at: null };
    }
    if (rest === 'admin/processes/' + PROCESS_ID) return withVersionSummary(processes[0]);
    if (rest === 'admin/business-actions') return Object.assign({}, businessActions[0], { id: '60000000-0000-4000-8000-000000000009', action_code: 'NEW_ACTION' });
    if (p1 === 'admin' && p2 === 'business-actions') return businessActions[0];
    if (p1 === 'admin' && p2 === 'process-versions' && p4 === 'graph') {
      return Object.assign(graphResponse(p3), { revision: 7 });
    }
    if (p1 === 'admin' && p2 === 'process-versions' && p4 === 'validate') {
      return { process_id: PROCESS_ID, version_id: p3, valid: true, issues: [] };
    }
    if (p1 === 'admin' && p2 === 'process-versions' && p4 === 'publish') {
      return Object.assign({}, withVersionSummary(processes[0]), { current_version_id: VERSION_V2, current_version_no: 2 });
    }
    if (p1 === 'processes' && p3 === 'instances') {
      return { instance_id: INSTANCE_RUNNING, status: 'RUNNING', process_id: p2, process_version_id: VERSION_V2, process_version_no: 2, current_node_name: '财务审批', pending_approver_person_ids: [PERSON_ZHANG, PERSON_ZHAO], started_at: at(0), idempotent_replay: false };
    }
    if (p1 === 'approval-tasks' && p2) {
      const isDone = p2 === TASK_DONE;
      return { instance_id: isDone ? INSTANCE_DONE : INSTANCE_RUNNING, instance_status: isDone ? 'APPROVED' : 'RUNNING', task_id: p2, task_status: p3 === 'reject' ? 'REJECTED' : 'APPROVED', node_execution_id: 'a1000000-0000-4000-8000-000000000002', node_execution_status: 'ACTIVE', current_node_name: '财务审批', idempotent_replay: false };
    }
    void method;
    return {};
  }

  /* ---------------------------------------------------------------------
     fetch 拦截
     --------------------------------------------------------------------- */

  let active = false;

  function intercept(url, options) {
    const method = ((options && options.method) || 'GET').toUpperCase();
    let path;
    try {
      path = new URL(url, location.href).pathname;
    } catch (err) {
      path = url;
    }

    const data = resolve(method, path);
    if (data === null || data === undefined) {
      return { ok: false, status: 404, text: async () => JSON.stringify({ detail: `示例数据没有覆盖该接口：${method} ${path}` }) };
    }

    if (method !== 'GET' && typeof window.toast === 'function') {
      window.toast('示例数据模式：本次操作不会真正保存', 'ok');
    }

    const payload = { code: 0, msg: 'success', data };
    return { ok: true, status: 200, text: async () => JSON.stringify(payload) };
  }

  const demo = {
    isOn() {
      return active;
    },
    enable() {
      if (active) return;
      active = true;
      const original = window.fetch.bind(window);
      this.originalFetch = original;
      window.fetch = (url, options) => {
        if (typeof url === 'string' && /\/api\//.test(url)) return Promise.resolve(intercept(url, options));
        return original(url, options);
      };
      localStorage.setItem('approval-console.demo', '1');
    },
    disable() {
      if (this.originalFetch) window.fetch = this.originalFetch;
      active = false;
      localStorage.removeItem('approval-console.demo');
    },
  };

  window.ApprovalDemo = demo;
  // 三种进入方式：接口失败时点按钮、地址栏加 ?demo=1、上次开启后记住的状态。
  const forced = /[?&]demo=1/.test(location.search || '') || /[?&]demo=1/.test(location.hash || '');
  if (forced || localStorage.getItem('approval-console.demo') === '1') demo.enable();
})();
