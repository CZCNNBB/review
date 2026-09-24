/** 接口返回的实体。字段与后端 Pydantic Schema 对齐。 */

import type { FlowConnection, FlowNode, JSONSchema, ValidationIssue } from '@/types/domain'

export interface Tenant {
  id: string
  code: string
  name: string
  description?: string | null
  callback_base_url: string
  status: string
  created_at: string
  updated_at: string
}

export interface TenantApiKey {
  id: string
  tenant_id: string
  name: string
  /** 只在签发的那一刻返回明文，列表接口不回显。 */
  api_key?: string | null
  status: string
  expires_at: string | null
  last_used_at: string | null
  created_at: string
  revoked_at: string | null
}

export interface CallbackCredential {
  id: string
  tenant_id: string
  name: string
  header_name: string
  token_prefix: string
  status: string
  expires_at: string | null
  created_at: string
  revoked_at: string | null
}

export interface Person {
  id: string
  name: string
  mobile?: string | null
  email?: string | null
  status: string
  created_at: string
  updated_at: string
}

export interface Department {
  id: string
  code: string
  name: string
  status: string
  created_at: string
  updated_at: string
}

export interface DepartmentMember {
  id: string
  department_id: string
  department_name: string
  person_id: string
  person_name: string
  status: string
  created_at: string
  updated_at: string
}

export interface TenantPersonBinding {
  binding_id: string
  tenant_id: string
  person_id: string
  person_name: string
  employee_no?: string | null
  external_user_id?: string | null
  display_name?: string | null
  status: string
  created_at: string
  updated_at: string
}

export interface Process {
  id: string
  name: string
  description?: string | null
  status: string
  current_version_id: string | null
  current_version_no: number | null
  draft_version_id: string | null
  draft_version_no: number | null
  node_count: number
  created_at: string
  updated_at: string
}

export interface ProcessVersion {
  id: string
  process_id: string
  version_no: number
  status: string
  name: string
  description?: string | null
  revision: number
  node_count: number
  created_at: string
  updated_at: string
  published_at: string | null
}

export interface ProcessGraph {
  process_id: string
  version_id: string
  version_no: number
  version_status: string
  revision: number
  name: string
  description: string | null
  form_schema: JSONSchema
  form_ui_schema: Record<string, unknown>
  orchestration: { connections?: FlowConnection[] }
  nodes: Array<FlowNode & { created_at?: string; updated_at?: string }>
  created_at: string
  updated_at: string
  published_at: string | null
}

export interface ValidationResult {
  valid: boolean
  issues: ValidationIssue[]
}

export interface BusinessAction {
  id: string
  action_code: string
  name: string
  description?: string | null
  http_method: string
  relative_path: string
  request_schema?: JSONSchema | null
  success_status_codes: number[]
  timeout_ms: number
  status: string
  created_at: string
  updated_at: string
}

export interface ProcessUsageRecord {
  id: string
  tenant_id: string
  process_id: string
  process_version_id: string
  approval_instance_id: string
  business_key: string
  action_code?: string | null
  created_at: string
  approval_status: string
  approval_title: string
  current_node_name: string | null
  started_at: string
  finished_at: string | null
  duration_ms: number | null
}

export interface ProcessBinding {
  id: string
  tenant_id: string
  process_id: string
  status: string
  created_at: string
  updated_at: string
}

export interface BusinessActionBinding {
  id: string
  tenant_id: string
  business_action_id: string
  status: string
  created_at: string
  updated_at: string
}

export interface ExecutionRecord {
  id: string
  approval_instance_id: string
  action_code: string
  http_method: string
  relative_path: string
  request_url: string | null
  request_payload: unknown
  response_body: string | null
  success_status_codes: number[] | null
  timeout_ms: number | null
  status: string
  http_status_code: number | null
  duration_ms: number | null
  error_message: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

/**
 * 审批运行侧的实体。
 *
 * 字段以后端 approval_schema.py 为准：详情是**平铺**的（不是 {instance: ...} 包一层），
 * 时间线是 `{entries: [{node_execution, tasks, records}]}` 这种按节点分组的结构。
 */

export interface ApprovalNodeExecution {
  id: string
  node_id: string
  node_type: string
  node_name: string
  sequence_no: number
  status: string
  entered_at: string
  completed_at: string | null
  duration_ms: number | null
  next_node_id: string | null
  next_node_name: string | null
  /** 条件分支节点才有：这一跳是命中条件还是走了兜底 */
  condition_hit: boolean | null
  result: Record<string, unknown>
}

export interface ApprovalTask {
  id: string
  instance_id: string
  node_execution_id: string
  instance_title: string | null
  business_key: string | null
  node_name: string | null
  approver_person_id: string
  approver_snapshot: Record<string, unknown>
  status: string
  created_at: string
  handled_at: string | null
  cancelled_at: string | null
  duration_ms: number | null
}

export interface ApprovalRecord {
  id: string
  instance_id: string
  node_execution_id: string
  task_id: string
  operator_person_id: string
  operator_snapshot: Record<string, unknown>
  /** APPROVE / REJECT */
  action: string
  comment: string | null
  created_at: string
  duration_ms: number | null
}

export interface ApprovalTimelineEntry {
  node_execution: ApprovalNodeExecution
  tasks: ApprovalTask[]
  records: ApprovalRecord[]
}

export interface ApprovalTimeline {
  instance_id: string
  title: string
  status: string
  started_at: string
  finished_at: string | null
  duration_ms: number | null
  entries: ApprovalTimelineEntry[]
}

export interface ApprovalInstanceDetail {
  id: string
  process_id: string
  process_name: string
  process_version_id: string
  process_version_no: number
  business_key: string
  title: string
  applicant_person_id: string | null
  applicant_snapshot: Record<string, unknown>
  action_code: string | null
  status: string
  approval_form: Record<string, unknown>
  current_node: ApprovalNodeExecution | null
  node_executions: ApprovalNodeExecution[]
  tasks: ApprovalTask[]
  records: ApprovalRecord[]
  pending_tasks: ApprovalTask[]
  started_at: string
  finished_at: string | null
  duration_ms: number | null
  created_at: string
  updated_at: string
}

/** 发起审批的结果。 */
export interface StartedInstance {
  instance_id: string
  status: string
  process_id: string
  process_version_id: string
  process_version_no: number
  current_node_name: string | null
  pending_approver_person_ids: string[]
  started_at: string
  idempotent_replay: boolean
}

/** 同意或拒绝之后返回的最新状态。 */
export interface ApprovalActionResult {
  instance_id: string
  instance_status: string
  task_id: string
  task_status: string
  node_execution_id: string
  node_execution_status: string
  current_node_name: string | null
  idempotent_replay: boolean
}

export interface TenantContext {
  tenant_id: string
  tenant_code: string
  tenant_name: string
  api_key_id: string
}
