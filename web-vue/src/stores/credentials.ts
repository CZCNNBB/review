import { defineStore } from 'pinia'
import { ref } from 'vue'

import { tenantApi } from '@/api/modules/tenant'
import type { ProcessUsageRecord, Tenant, TenantApiKey } from '@/api/types'

/**
 * 管理台自动借用租户密钥（契约⑧）。
 *
 * 审批详情、时间线、待办任务、发起审批在租户模式下都要求 X-API-Key，而管理员只填了一个
 * 管理密钥。这里按「审批使用记录 → 租户 → 该租户的有效 API Key」自动解析，并把结果按
 * 会话缓存 —— 这条链路是逐租户扇出查询的，不缓存会把接口打爆。
 *
 * 唯一需要缓存的一组数据。任何写操作后调用 invalidate() 重取。
 */
export const useCredentialsStore = defineStore('credentials', () => {
  const tenants = ref<Tenant[] | null>(null)
  const apiKeys = ref<Record<string, TenantApiKey[]>>({})
  const usage = ref<Record<string, ProcessUsageRecord[]>>({})

  function invalidate(): void {
    tenants.value = null
    apiKeys.value = {}
    usage.value = {}
  }

  async function loadTenants(): Promise<Tenant[]> {
    if (!tenants.value) tenants.value = await tenantApi.list(200)
    return tenants.value
  }

  async function tenantApiKeys(tenantId: string): Promise<TenantApiKey[]> {
    if (!apiKeys.value[tenantId]) {
      try {
        apiKeys.value[tenantId] = await tenantApi.apiKeys(tenantId)
      } catch {
        // 列表页的局部失败不该让整页崩掉，当作没有密钥处理
        apiKeys.value[tenantId] = []
      }
    }
    return apiKeys.value[tenantId]
  }

  /** 取该租户第一个启用中的密钥；没有可用的返回 null。 */
  async function tenantApiKey(tenantId: string): Promise<string | null> {
    const keys = await tenantApiKeys(tenantId)
    const usable = keys.find((item) => item.status === 'ENABLED')
    return usable?.api_key || null
  }

  /** 使用记录是判断「这张审批单属于哪个租户」的唯一依据。 */
  async function tenantUsageRecords(tenantId: string): Promise<ProcessUsageRecord[]> {
    if (!usage.value[tenantId]) {
      try {
        usage.value[tenantId] = await tenantApi.usageRecords(tenantId, 500)
      } catch {
        usage.value[tenantId] = []
      }
    }
    return usage.value[tenantId]
  }

  async function tenantOfInstance(instanceId: string): Promise<Tenant | null> {
    const list = await loadTenants()
    for (const tenant of list) {
      const records = await tenantUsageRecords(tenant.id)
      if (records.some((record) => record.approval_instance_id === instanceId)) return tenant
    }
    return null
  }

  /** 审批实例对应的租户与可借用的密钥，供查询详情和代办操作使用。 */
  async function forInstance(
    instanceId: string,
  ): Promise<{ tenant: Tenant | null; key: string | null }> {
    const tenant = await tenantOfInstance(instanceId)
    if (!tenant) return { tenant: null, key: null }
    return { tenant, key: await tenantApiKey(tenant.id) }
  }

  return {
    tenants,
    apiKeys,
    usage,
    invalidate,
    loadTenants,
    tenantApiKeys,
    tenantApiKey,
    tenantUsageRecords,
    tenantOfInstance,
    forInstance,
  }
})
