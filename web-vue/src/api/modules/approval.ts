import { endpoints } from '../endpoints'
import { api } from '../http'
import type {
  ApprovalActionResult,
  ApprovalInstanceDetail,
  ApprovalTask,
  ApprovalTimeline,
  StartedInstance,
  TenantContext,
} from '../types'

export interface StartInstanceInput {
  business_key: string
  title: string
  applicant_person_id?: string | null
  action_code?: string | null
  approval_form?: Record<string, unknown>
  execution_payload?: Record<string, unknown>
}

export interface TaskDecisionInput {
  /** 以哪个审批人的身份处理（管理台代审批）。 */
  person_id: string
  comment?: string | null
}

export const approvalApi = {
  /** 校验一个租户密钥是否可用，顺带拿到租户上下文。 */
  tenantContext: (apiKey: string) =>
    api.get<TenantContext>(endpoints.tenantContext, 'apikey', apiKey),

  start: (processId: string, input: StartInstanceInput, apiKey?: string) =>
    api.post<StartedInstance>(endpoints.startInstance(processId), input, 'apikey', apiKey),

  tasks: (personId: string, status?: string) =>
    api.get<ApprovalTask[]>(endpoints.approvalTasks(personId, status)),

  approve: (taskId: string, input: TaskDecisionInput) =>
    api.post<ApprovalActionResult>(endpoints.approveTask(taskId), input),

  reject: (taskId: string, input: TaskDecisionInput) =>
    api.post<ApprovalActionResult>(endpoints.rejectTask(taskId), input),

  instance: (id: string, apiKey?: string) =>
    api.get<ApprovalInstanceDetail>(endpoints.approvalInstance(id), 'apikey', apiKey),

  timeline: (id: string, apiKey?: string) =>
    api.get<ApprovalTimeline>(endpoints.instanceTimeline(id), 'apikey', apiKey),
}
