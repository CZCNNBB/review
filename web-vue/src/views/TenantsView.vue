<script setup lang="ts">
import { ElButton } from 'element-plus'
import { onMounted, ref } from 'vue'

import { tenantApi } from '@/api/modules/tenant'
import type { Tenant } from '@/api/types'
import DataTable from '@/components/common/DataTable.vue'
import type { ColumnSpec } from '@/components/common/DataTable.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import TenantFormDialog from '@/components/dialogs/TenantFormDialog.vue'
import ErrorPanel from '@/components/layout/ErrorPanel.vue'
import PageHead from '@/components/layout/PageHead.vue'
import PanelCard from '@/components/layout/PanelCard.vue'
import { useAsyncPage } from '@/composables/useAsyncPage'
import { useCredentialsStore } from '@/stores/credentials'
import { useShellStore } from '@/stores/shell'
import { formatTime } from '@/utils/format'

const columns: ColumnSpec[] = [
  { key: 'code', title: '编码', width: 120 },
  { key: 'name', title: '名称', width: 160 },
  { key: 'callback_base_url', title: '回调基础地址' },
  { key: 'status', title: '状态', width: 90 },
  { key: 'created_at', title: '创建时间', width: 160 },
  { key: 'actions', title: '操作', width: 150, align: 'right' },
]

const shell = useShellStore()
const credentials = useCredentialsStore()

// 解构出来用：模板里 ref 会自动解包，不必到处写 .value
const {
  data: tenants,
  loading,
  error,
  refresh,
} = useAsyncPage(async () => {
  const list = await tenantApi.list(200)
  shell.setCount('tenants', list.length)
  return list
}, [] as Tenant[])

const dialogOpen = ref(false)
const editing = ref<Tenant | null>(null)

function openCreate(): void {
  editing.value = null
  dialogOpen.value = true
}

function openEdit(tenant: Tenant): void {
  // 旧版列表里的「编辑」按钮没有对应处理函数，点了没反应；这里补上。
  editing.value = tenant
  dialogOpen.value = true
}

async function afterSaved(): Promise<void> {
  // 租户变了，密钥借用缓存立刻失效
  credentials.invalidate()
  await refresh()
}

onMounted(refresh)
</script>

<template>
  <PageHead
    title="租户"
    note="租户代表一个接入的业务系统。API Key 用于发起审批，回调凭据用于审批通过后回调业务系统。"
  >
    <ElButton type="primary" @click="openCreate">新建租户</ElButton>
  </PageHead>

  <ErrorPanel v-if="error" :error="error" />

  <PanelCard v-else>
    <DataTable
      :columns="columns"
      :rows="tenants"
      :loading="loading"
      empty-title="还没有租户"
      empty-hint="先建一个租户并签发 API Key，业务系统才能发起审批。"
    >
      <template #cell-callback_base_url="{ row }">
        <span class="code">{{ row.callback_base_url }}</span>
      </template>
      <template #cell-status="{ row }">
        <StatusTag :status="row.status" />
      </template>
      <template #cell-created_at="{ row }">
        {{ formatTime(row.created_at) }}
      </template>
      <template #cell-actions="{ row }">
        <a class="btn--link btn--sm" :href="`#/tenants/${row.id}`">接入凭据</a>
        <button class="btn--link btn--sm" type="button" @click="openEdit(row)">编辑</button>
      </template>
      <template #empty-action>
        <ElButton type="primary" size="small" @click="openCreate">新建租户</ElButton>
      </template>
    </DataTable>
  </PanelCard>

  <TenantFormDialog v-model:open="dialogOpen" :tenant="editing" @saved="afterSaved" />
</template>
