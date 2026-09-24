import { endpoints } from '../endpoints'
import { api } from '../http'
import type { BusinessActionBinding, ProcessBinding } from '../types'

/** 资源授权：把审批流与业务动作授权给租户。 */
export const grantApi = {
  processBindings: (tenantId: string) =>
    api.get<ProcessBinding[]>(endpoints.processBindings(tenantId)),

  bindProcess: (tenantId: string, input: { process_id: string; status?: string }) =>
    api.post<ProcessBinding>(endpoints.processBindings(tenantId), input),

  updateProcessBinding: (tenantId: string, bindingId: string, status: string) =>
    api.patch<ProcessBinding>(endpoints.processBinding(tenantId, bindingId), { status }),

  actionBindings: (tenantId: string) =>
    api.get<BusinessActionBinding[]>(endpoints.actionBindings(tenantId)),

  bindAction: (tenantId: string, input: { business_action_id: string; status?: string }) =>
    api.post<BusinessActionBinding>(endpoints.actionBindings(tenantId), input),

  updateActionBinding: (tenantId: string, bindingId: string, status: string) =>
    api.patch<BusinessActionBinding>(endpoints.actionBinding(tenantId, bindingId), { status }),
}
