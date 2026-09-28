import { endpoints } from '../endpoints'
import { api } from '../http'
import type {
  ApprovalActionResult,
  ApprovalCopy,
  ApprovalInstanceDetail,
  ApprovalTask,
  ApprovalTimeline,
  ApprovalWorkItem,
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

  /** 默认查询全部抄送记录，也可只看指定人员。 */
  copies: (personId?: string) =>
    api.get<ApprovalCopy[]>(endpoints.approvalCopies(personId)),

  /** 从统一任务表查询审批与抄送工作台。 */
  workItems: (offset = 0) =>
    api.get<ApprovalWorkItem[]>(endpoints.workItems(offset)),

  /** 从抄送记录打开审批单，只提供查看能力。 */
  copiedInstance: (copyId: string, personId: string) =>
    api.get<ApprovalInstanceDetail>(endpoints.approvalCopyInstance(copyId, personId)),

  approve: (taskId: string, input: TaskDecisionInput) =>
    api.post<ApprovalActionResult>(endpoints.approveTask(taskId), input),

  reject: (taskId: string, input: TaskDecisionInput) =>
    api.post<ApprovalActionResult>(endpoints.rejectTask(taskId), input),

  instance: (id: string, apiKey?: string) =>
    api.get<ApprovalInstanceDetail>(endpoints.approvalInstance(id), 'apikey', apiKey),

  timeline: (id: string, apiKey?: string) =>
    api.get<ApprovalTimeline>(endpoints.instanceTimeline(id), 'apikey', apiKey),
}
