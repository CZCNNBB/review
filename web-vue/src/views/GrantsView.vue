<script setup lang="ts">
import { ElButton, ElOption, ElSelect } from 'element-plus'
import { onMounted, ref, watch } from 'vue'

import { safe } from '@/api/http'
import { actionApi } from '@/api/modules/action'
import { grantApi } from '@/api/modules/grant'
import { processApi } from '@/api/modules/process'
import type {
  BusinessAction,
  BusinessActionBinding,
  Process,
  ProcessBinding,
  Tenant,
} from '@/api/types'
import DataTable from '@/components/common/DataTable.vue'
import type { ColumnSpec } from '@/components/common/DataTable.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import GrantBindingDialog from '@/components/dialogs/GrantBindingDialog.vue'
import EmptyState from '@/components/layout/EmptyState.vue'
import ErrorPanel from '@/components/layout/ErrorPanel.vue'
import PageHead from '@/components/layout/PageHead.vue'
import PanelCard from '@/components/layout/PanelCard.vue'
import { useAsyncPage } from '@/composables/useAsyncPage'
import { errorMessageOf } from '@/composables/useConfirm'
import { useUrlFilters } from '@/composables/useUrlFilters'
import { useCredentialsStore } from '@/stores/credentials'
import { useShellStore } from '@/stores/shell'
import { formatTime, shortId } from '@/utils/format'
import { toastError, toastOk } from '@/utils/notify'

/** 授权接口是租户维度的，合并成一张表时要自己带上租户名。 */
type ProcessBindingRow = ProcessBinding & { tenant_name: string }
type ActionBindingRow = BusinessActionBinding & { tenant_name: string }

interface GrantsData {
  tenants: Tenant[]
  processes: Process[]
  actions: BusinessAction[]
  processRows: ProcessBindingRow[]
  actionRows: ActionBindingRow[]
}

const EMPTY: GrantsData = {
  tenants: [],
  processes: [],
  actions: [],
  processRows: [],
  actionRows: [],
}

const processColumns: ColumnSpec[] = [
  { key: 'tenant_name', title: '租户', width: 150 },
  { key: 'process_id', title: '审批流' },
  { key: 'process_short_id', title: '流程 ID', width: 110 },
  { key: 'status', title: '状态', width: 90 },
  { key: 'created_at', title: '授权时间', width: 140 },
  { key: 'actions', title: '操作', width: 80, align: 'right' },
]

const actionColumns: ColumnSpec[] = [
  { key: 'tenant_name', title: '租户', width: 150 },
  { key: 'business_action_id', title: '业务动作' },
  { key: 'action_short_id', title: '动作 ID', width: 110 },
  { key: 'status', title: '状态', width: 90 },
  { key: 'created_at', title: '授权时间', width: 140 },
  { key: 'actions', title: '操作', width: 80, align: 'right' },
]

function withTenantName<T extends { tenant_id: string }>(
  groups: T[][],
  names: string[],
): Array<T & { tenant_name: string }> {
  return groups.flatMap((list, index) =>
    list.map((item) => ({ ...item, tenant_name: names[index] })),
  )
}

const shell = useShellStore()
const credentials = useCredentialsStore()
const tenantFilter = useUrlFilters().filter('tenant')

const { data, loading, error, refresh } = useAsyncPage<GrantsData>(async () => {
  // 租户都没拉到时整页没有意义，这一项不兜底，交给错误面板（旧版同样如此）
  const tenants = await credentials.loadTenants()
  const [processes, actions] = await Promise.all([
    safe(processApi.processes(200), []),
    safe(actionApi.list(200), []),
  ])

  // 授权没有全局列表接口：按租户扇出查询再合并（旧版策略，保持）。
  // URL 里的租户取不到（链接指向已删租户）时按「全部租户」处理，否则会得到一张
  // 看起来「没有任何授权」的空表，和页头下拉显示的内容自相矛盾。
  const picked = tenants.find((item) => item.id === tenantFilter.value)
  const targets = picked ? [picked] : tenants

  const [processGroups, actionGroups] = await Promise.all([
    Promise.all(targets.map((tenant) => safe(grantApi.processBindings(tenant.id), []))),
    Promise.all(targets.map((tenant) => safe(grantApi.actionBindings(tenant.id), []))),
  ])
  const names = targets.map((tenant) => tenant.name)

  shell.setCount('grants', processGroups.flat().length + actionGroups.flat().length)

  return {
    tenants,
    processes,
    actions,
    processRows: withTenantName(processGroups, names),
    actionRows: withTenantName(actionGroups, names),
  }
}, EMPTY)

// 换租户只是一次新查询，筛选条件是地址栏那一份，页面不另存一份真相
watch(tenantFilter, () => void refresh())

function processName(id: string): string {
  const process = data.value.processes.find((item) => item.id === id)
  return process ? process.name : shortId(id)
}

function actionName(id: string): string {
  const action = data.value.actions.find((item) => item.id === id)
  return action ? `${action.name}（${action.action_code}）` : shortId(id)
}

const dialogOpen = ref(false)
const dialogMode = ref<'process' | 'action'>('process')

function openGrant(mode: 'process' | 'action'): void {
  dialogMode.value = mode
  dialogOpen.value = true
}

/** 停用/启用一条授权。停用不影响已经跑起来的审批实例（旧版提示同此）。 */
async function toggleProcessBinding(row: ProcessBindingRow): Promise<void> {
  const next = row.status === 'ENABLED' ? 'DISABLED' : 'ENABLED'
  try {
    await grantApi.updateProcessBinding(row.tenant_id, row.id, next)
    toastOk('授权状态已更新')
    await refresh()
  } catch (err) {
    toastError(errorMessageOf(err))
  }
}

async function toggleActionBinding(row: ActionBindingRow): Promise<void> {
  const next = row.status === 'ENABLED' ? 'DISABLED' : 'ENABLED'
  try {
    await grantApi.updateActionBinding(row.tenant_id, row.id, next)
    toastOk('授权状态已更新')
    await refresh()
  } catch (err) {
    toastError(errorMessageOf(err))
  }
}

onMounted(refresh)
</script>

<template>
  <PageHead
    title="资源授权"
    note="全部租户的授权关系合并展示。授权只决定租户能否使用某个流程或动作，不覆盖流程内部的版本、节点和审批人配置；停用授权不影响已经运行的审批实例。"
  >
    <ElSelect
      v-if="data.tenants.length"
      v-model="tenantFilter"
      placeholder="全部租户"
      style="width: 180px"
    >
      <ElOption value="" label="全部租户" />
      <ElOption
        v-for="tenant in data.tenants"
        :key="tenant.id"
        :value="tenant.id"
        :label="tenant.name"
      />
    </ElSelect>
  </PageHead>

  <ErrorPanel v-if="error" :error="error" />

  <PanelCard v-else-if="!data.tenants.length">
    <EmptyState title="还没有租户" hint="先创建租户，再回来配置授权。">
      <a class="btn btn--sm" href="#/tenants">去创建租户</a>
    </EmptyState>
  </PanelCard>

  <template v-else>
    <PanelCard title="审批流授权">
      <template #actions>
        <ElButton type="primary" size="small" @click="openGrant('process')">授权审批流</ElButton>
      </template>
      <DataTable
        :columns="processColumns"
        :rows="data.processRows"
        :loading="loading"
        empty-title="还没有审批流授权"
        empty-hint="授权后业务系统才能用这条流程发起审批。"
      >
        <template #cell-tenant_name="{ row }">
          <span class="cell-title">{{ row.tenant_name }}</span>
        </template>
        <template #cell-process_id="{ row }">
          {{ processName(row.process_id) }}
        </template>
        <template #cell-process_short_id="{ row }">
          <span class="code">{{ shortId(row.process_id) }}</span>
        </template>
        <template #cell-status="{ row }">
          <StatusTag :status="row.status" />
        </template>
        <template #cell-created_at="{ row }">
          <span class="muted">{{ formatTime(row.created_at) }}</span>
        </template>
        <template #cell-actions="{ row }">
          <button class="btn--link btn--sm" type="button" @click="toggleProcessBinding(row)">
            {{ row.status === 'ENABLED' ? '停用' : '启用' }}
          </button>
        </template>
      </DataTable>
    </PanelCard>

    <PanelCard title="业务动作授权">
      <template #actions>
        <ElButton type="primary" size="small" @click="openGrant('action')">授权业务动作</ElButton>
      </template>
      <DataTable
        :columns="actionColumns"
        :rows="data.actionRows"
        :loading="loading"
        empty-title="还没有业务动作授权"
        empty-hint="只有需要审批通过后回调业务系统的租户才需要配置。"
      >
        <template #cell-tenant_name="{ row }">
          <span class="cell-title">{{ row.tenant_name }}</span>
        </template>
        <template #cell-business_action_id="{ row }">
          {{ actionName(row.business_action_id) }}
        </template>
        <template #cell-action_short_id="{ row }">
          <span class="code">{{ shortId(row.business_action_id) }}</span>
        </template>
        <template #cell-status="{ row }">
          <StatusTag :status="row.status" />
        </template>
        <template #cell-created_at="{ row }">
          <span class="muted">{{ formatTime(row.created_at) }}</span>
        </template>
        <template #cell-actions="{ row }">
          <button class="btn--link btn--sm" type="button" @click="toggleActionBinding(row)">
            {{ row.status === 'ENABLED' ? '停用' : '启用' }}
          </button>
        </template>
      </DataTable>
    </PanelCard>
  </template>

  <GrantBindingDialog
    v-model:open="dialogOpen"
    :mode="dialogMode"
    :tenants="data.tenants"
    :processes="data.processes"
    :actions="data.actions"
    @saved="refresh"
  />
</template>

<style scoped>
.muted {
  color: var(--ink-3);
}
/* 旧版的 .cell-title 只写在 .tbl 作用域里，AntD 的表格里匹配不到，这里补一条 */
.cell-title {
  font-weight: 600;
}
</style>
