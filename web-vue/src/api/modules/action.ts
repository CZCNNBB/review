import type { JSONSchema } from '@/types/domain'

import { endpoints } from '../endpoints'
import { api } from '../http'
import type { BusinessAction, BusinessActionBinding, ExecutionRecord } from '../types'

export interface BusinessActionInput {
  action_code?: string
  name: string
  description?: string | null
  http_method?: string
  relative_path: string
  request_schema_json?: JSONSchema | null
  success_status_codes?: number[]
  timeout_ms?: number
  status?: string
}

export const actionApi = {
  list: (limit = 200) => api.get<BusinessAction[]>(endpoints.businessActions(limit)),

  create: (input: BusinessActionInput) =>
    api.post<BusinessAction>(endpoints.businessActions(1).split('?')[0], input),

  update: (id: string, input: Partial<BusinessActionInput>) =>
    api.patch<BusinessAction>(endpoints.businessAction(id), input),

  executionRecords: (params: { limit?: number; status?: string; instanceId?: string } = {}) =>
    api.get<ExecutionRecord[]>(endpoints.executionRecords(params)),

  executionRecord: (id: string) => api.get<ExecutionRecord>(endpoints.executionRecord(id)),

  updateBinding: (tenantId: string, bindingId: string, status: string) =>
    api.patch<BusinessActionBinding>(endpoints.actionBinding(tenantId, bindingId), { status }),
}
