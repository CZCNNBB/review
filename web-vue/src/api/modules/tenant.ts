import { endpoints } from '../endpoints'
import { api } from '../http'
import type {
  CallbackCredential,
  ProcessUsageRecord,
  Tenant,
  TenantApiKey,
} from '../types'

export interface TenantInput {
  code?: string
  name: string
  callback_base_url: string
  description?: string | null
  status?: string
}

export interface ApiKeyInput {
  name: string
  expires_at?: string | null
}

export interface CredentialInput {
  name: string
  token: string
  header_name?: string
  token_prefix?: string
  expires_at?: string | null
}

export const tenantApi = {
  list: (limit = 200) => api.get<Tenant[]>(endpoints.tenants(limit)),

  get: (id: string) => api.get<Tenant>(endpoints.tenant(id)),

  create: (input: TenantInput) => api.post<Tenant>(endpoints.tenants(1).split('?')[0], input),

  update: (id: string, input: Partial<TenantInput>) =>
    api.patch<Tenant>(endpoints.tenant(id), input),

  apiKeys: (id: string) => api.get<TenantApiKey[]>(endpoints.tenantApiKeys(id)),

  issueApiKey: (id: string, input: ApiKeyInput) =>
    api.post<TenantApiKey>(endpoints.tenantApiKeys(id), input),

  revokeApiKey: (id: string, keyId: string) => api.post<unknown>(endpoints.revokeApiKey(id, keyId)),

  credentials: (id: string) => api.get<CallbackCredential[]>(endpoints.tenantCredentials(id)),

  createCredential: (id: string, input: CredentialInput) =>
    api.post<CallbackCredential>(endpoints.tenantCredentials(id), input),

  revokeCredential: (id: string, credentialId: string) =>
    api.post<unknown>(endpoints.revokeCredential(id, credentialId)),

  usageRecords: (id: string, limit = 200, businessKey?: string) =>
    api.get<ProcessUsageRecord[]>(endpoints.tenantUsageRecords(id, limit, businessKey)),
}
