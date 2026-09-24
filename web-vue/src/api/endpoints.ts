/**
 * 接口路径集中在这里，页面里不再手写模板字符串。
 * 路径与后端 api/*.py 的路由一一对应（全部挂在 /api 下）。
 */
const ADMIN = '/api/admin'

export const endpoints = {
  // 租户与接入凭据
  tenants: (limit = 200) => `${ADMIN}/tenants?limit=${limit}`,
  tenant: (id: string) => `${ADMIN}/tenants/${id}`,
  tenantApiKeys: (id: string) => `${ADMIN}/tenants/${id}/api-keys`,
  revokeApiKey: (id: string, keyId: string) => `${ADMIN}/tenants/${id}/api-keys/${keyId}/revoke`,
  tenantCredentials: (id: string) => `${ADMIN}/tenants/${id}/callback-credentials`,
  revokeCredential: (id: string, credentialId: string) =>
    `${ADMIN}/tenants/${id}/callback-credentials/${credentialId}/revoke`,
  tenantUsageRecords: (id: string, limit = 200, businessKey?: string) =>
    `${ADMIN}/tenants/${id}/process-usage-records?limit=${limit}` +
    (businessKey ? `&business_key=${encodeURIComponent(businessKey)}` : ''),
  tenantPersons: (id: string) => `${ADMIN}/tenants/${id}/persons`,
  bindTenantPerson: (id: string) => `${ADMIN}/tenants/${id}/persons/bind`,
  tenantPersonBinding: (id: string, personId: string) =>
    `${ADMIN}/tenants/${id}/persons/${personId}/binding`,

  // 人员与部门
  persons: (limit = 200) => `${ADMIN}/persons?limit=${limit}`,
  person: (id: string) => `${ADMIN}/persons/${id}`,
  departments: (limit = 200) => `${ADMIN}/departments?limit=${limit}`,
  departmentMembers: (id: string) => `${ADMIN}/departments/${id}/members`,
  disableDepartmentMember: (id: string, personId: string) =>
    `${ADMIN}/departments/${id}/members/${personId}/disable`,

  // 审批流与版本
  processes: (limit = 200) => `${ADMIN}/processes?limit=${limit}`,
  process: (id: string) => `${ADMIN}/processes/${id}`,
  copyProcess: (id: string) => `${ADMIN}/processes/${id}/copy`,
  disableProcess: (id: string) => `${ADMIN}/processes/${id}/disable`,
  processDraft: (id: string) => `${ADMIN}/processes/${id}/draft`,
  processVersions: (id: string) => `${ADMIN}/processes/${id}/versions`,
  versionGraph: (id: string) => `${ADMIN}/process-versions/${id}/graph`,
  validateVersion: (id: string) => `${ADMIN}/process-versions/${id}/validate`,
  publishVersion: (id: string) => `${ADMIN}/process-versions/${id}/publish`,

  // 节点定义（只读：清单在代码里，后端启动时同步）
  nodeDefinitions: (limit = 100) => `${ADMIN}/node-definitions?limit=${limit}`,

  // 业务动作与执行
  businessActions: (limit = 200) => `${ADMIN}/business-actions?limit=${limit}`,
  businessAction: (id: string) => `${ADMIN}/business-actions/${id}`,
  executionRecords: (params: { limit?: number; status?: string; instanceId?: string } = {}) => {
    const query = new URLSearchParams({ limit: String(params.limit ?? 200) })
    if (params.status) query.set('status', params.status)
    if (params.instanceId) query.set('approval_instance_id', params.instanceId)
    return `${ADMIN}/execution-records?${query.toString()}`
  },
  executionRecord: (id: string) => `${ADMIN}/execution-records/${id}`,

  // 资源授权
  processBindings: (tenantId: string) => `${ADMIN}/tenants/${tenantId}/process-bindings`,
  processBinding: (tenantId: string, bindingId: string) =>
    `${ADMIN}/tenants/${tenantId}/process-bindings/${bindingId}`,
  actionBindings: (tenantId: string) => `${ADMIN}/tenants/${tenantId}/business-action-bindings`,
  actionBinding: (tenantId: string, bindingId: string) =>
    `${ADMIN}/tenants/${tenantId}/business-action-bindings/${bindingId}`,

  // 运行侧（租户密钥）
  tenantContext: '/api/tenant/context',
  startInstance: (processId: string) => `/api/processes/${processId}/instances`,
  approvalTasks: (personId: string, status?: string) =>
    `/api/approval-tasks?person_id=${encodeURIComponent(personId)}` +
    (status ? `&status=${encodeURIComponent(status)}` : '') +
    '&limit=200',
  approveTask: (taskId: string) => `/api/approval-tasks/${taskId}/approve`,
  rejectTask: (taskId: string) => `/api/approval-tasks/${taskId}/reject`,
  approvalInstance: (id: string) => `/api/approval-instances/${id}`,
  instanceTimeline: (id: string) => `/api/approval-instances/${id}/timeline`,
} as const
