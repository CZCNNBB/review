import { endpoints } from '../endpoints'
import { api } from '../http'
import type {
  ApprovalActionResult,
  ApprovalInstanceDetail,
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
  action: 'APPROVE' | 'REJECT'
  comment?: string | null
}

export const approvalApi = {
  /** 校验一个租户密钥是否可用，顺带拿到租户上下文。 */
  tenantContext: (apiKey: string) =>
    api.get<TenantContext>(endpoints.tenantContext, 'apikey', apiKey),

  start: (processId: string, input: StartInstanceInput, apiKey?: string) =>
    api.post<StartedInstance>(endpoints.startInstance(processId), input, 'apikey', apiKey),

  /** 按接收人、类型、状态筛选统一任务表，并按收件时间分页。 */
  workItems: (params: { personId?: string; taskType?: string; status?: string; offset: number }) =>
    api.get<ApprovalWorkItem[]>(endpoints.workItems(params)),

  /** 按统一任务 ID 打开审批单，适用于审批和抄送任务。 */
  workItemInstance: (taskId: string, personId: string) =>
    api.get<ApprovalInstanceDetail>(endpoints.workItemInstance(taskId, personId)),

  /** 审批结果作为参数提交到统一任务处理接口。 */
  decide: (taskId: string, input: TaskDecisionInput) =>
    api.post<ApprovalActionResult>(endpoints.decideTask(taskId), input),

  instance: (id: string, apiKey?: string) =>
    api.get<ApprovalInstanceDetail>(endpoints.approvalInstance(id), 'apikey', apiKey),

}
