<script setup lang="ts">
import { ElButton } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { safe } from '@/api/http'
import { actionApi } from '@/api/modules/action'
import { grantApi } from '@/api/modules/grant'
import { processApi } from '@/api/modules/process'
import { tenantApi } from '@/api/modules/tenant'
import type {
  BusinessAction,
  BusinessActionBinding,
  CallbackCredential,
  Process,
  ProcessBinding,
  ProcessUsageRecord,
  Tenant,
  TenantApiKey,
} from '@/api/types'
import CopyButton from '@/components/common/CopyButton.vue'
import DataTable from '@/components/common/DataTable.vue'
import type { ColumnSpec } from '@/components/common/DataTable.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import ApiKeyDialog from '@/components/dialogs/ApiKeyDialog.vue'
import CallbackCredentialDialog from '@/components/dialogs/CallbackCredentialDialog.vue'
import GrantBindingDialog from '@/components/dialogs/GrantBindingDialog.vue'
import TenantFormDialog from '@/components/dialogs/TenantFormDialog.vue'
import Breadcrumb from '@/components/layout/Breadcrumb.vue'
import ErrorPanel from '@/components/layout/ErrorPanel.vue'
import KvDescriptions from '@/components/layout/KvDescriptions.vue'
import PageHead from '@/components/layout/PageHead.vue'
import PanelCard from '@/components/layout/PanelCard.vue'
import { useAsyncPage } from '@/composables/useAsyncPage'
import { confirmAction, errorMessageOf } from '@/composables/useConfirm'
import { useCredentialsStore } from '@/stores/credentials'
import { formatDuration, formatTime } from '@/utils/format'
import { actionGrantRows, processGrantRows, type GrantRow } from '@/utils/grantRows'
import { toastError, toastOk } from '@/utils/notify'
import { isActive } from '@/utils/status'

const apiKeyColumns: ColumnSpec[] = [
  { key: 'name', title: '用途', width: 160 },
  { key: 'api_key', title: '密钥' },
  { key: 'status', title: '状态', width: 90 },
  { key: 'last_used_at', title: '最近使用', width: 160 },
  { key: 'expires_at', title: '过期时间', width: 160 },
  { key: 'actions', title: '操作', width: 150, align: 'right' },
]

const credentialColumns: ColumnSpec[] = [
  { key: 'name', title: '用途', width: 160 },
  { key: 'header_name', title: '认证请求头', width: 240 },
  { key: 'status', title: '状态', width: 90 },
  { key: 'expires_at', title: '过期时间', width: 160 },
  { key: 'actions', title: '操作', width: 100, align: 'right' },
]

const grantColumns: ColumnSpec[] = [
  { key: 'name', title: '资源' },
  { key: 'resourceShortId', title: '资源 ID', width: 110 },
  { key: 'status', title: '授权状态', width: 100 },
  { key: 'created_at', title: '授权时间', width: 160 },
  { key: 'actions', title: '操作', width: 90, align: 'right' },
]

const usageColumns: ColumnSpec[] = [
  { key: 'created_at', title: '发起时间', width: 160 },
  { key: 'approval_title', title: '审批单' },
  { key: 'business_key', title: '业务单号', width: 180 },
  { key: 'action_code', title: '业务动作', width: 150 },
  { key: 'approval_status', title: '审批状态', width: 100 },
  { key: 'current_node_name', title: '当前节点', width: 150 },
  { key: 'duration_ms', title: '耗时', width: 100 },
  { key: 'actions', title: '操作', width: 110, align: 'right' },
]

const route = useRoute()
const tenantId = computed(() => String(route.params.id || ''))

const credentials = useCredentialsStore()

const {
  data: page,
  loading,
  error,
  refresh,
} = useAsyncPage(
  async () => {
    const [tenant, apiKeys, callbackCredentials, usages, processBindings, actionBindings, processes, actions] =
      await Promise.all([
        tenantApi.get(tenantId.value),
        tenantApi.apiKeys(tenantId.value),
        // 凭据与使用记录是辅助信息：单独失败不该把整页变成错误面板（旧版就是 safe 兜底）
        safe(tenantApi.credentials(tenantId.value), [] as CallbackCredential[]),
        safe(tenantApi.usageRecords(tenantId.value, 20), [] as ProcessUsageRecord[]),
        // 授权和资源表同理兜底：拿不到就显示空授权，不要把整页变成错误面板
        safe(grantApi.processBindings(tenantId.value), [] as ProcessBinding[]),
        safe(grantApi.actionBindings(tenantId.value), [] as BusinessActionBinding[]),
        // 资源表只为把绑定里的 UUID 翻成名字（后端没有按 id 批量查的接口）
        safe(processApi.processes(200), [] as Process[]),
        safe(actionApi.list(200), [] as BusinessAction[]),
      ])
    return {
      tenant,
      apiKeys,
      callbackCredentials,
      usages,
      processBindings,
      actionBindings,
      processes,
      actions,
    }
  },
  {
    tenant: null as Tenant | null,
    apiKeys: [] as TenantApiKey[],
    callbackCredentials: [] as CallbackCredential[],
    usages: [] as ProcessUsageRecord[],
    processBindings: [] as ProcessBinding[],
    actionBindings: [] as BusinessActionBinding[],
    processes: [] as Process[],
    actions: [] as BusinessAction[],
  },
)

const tenant = computed(() => page.value.tenant)
const apiKeys = computed(() => page.value.apiKeys)
const callbackCredentials = computed(() => page.value.callbackCredentials)
const usages = computed(() => page.value.usages)
const processGrants = computed(() => processGrantRows(page.value.processBindings, page.value.processes))
const actionGrants = computed(() => actionGrantRows(page.value.actionBindings, page.value.actions))

const basicPairs = computed(() => [
  { key: '租户 ID', slot: 'tenantId' },
  { key: '回调基础地址', slot: 'callbackBaseUrl' },
  { key: '说明', value: tenant.value?.description || '—' },
  { key: '创建时间', value: formatTime(tenant.value?.created_at) },
])

const tenantDialogOpen = ref(false)
const apiKeyDialogOpen = ref(false)
const credentialDialogOpen = ref(false)

/** 认证头的展示形态：Authorization: Bearer *** ／ Authorization: ***（无前缀时直接放明文） */
function headerPreview(credential: CallbackCredential): string {
  return `${credential.header_name}:${credential.token_prefix ? ` ${credential.token_prefix}` : ''} ***`
}

/** 审批单详情链接，与「使用记录」页同一条路由 */
function instanceHref(record: ProcessUsageRecord): string {
  return `#/instances/${record.approval_instance_id}`
}

// 同组件复用（从一个租户点进另一个租户）时参数变了必须重取：旧版靠 hash 变化整体重渲染
watch(tenantId, () => void refresh())

onMounted(refresh)

async function afterSaved(): Promise<void> {
  // 租户或密钥变了，别处借用的密钥缓存立刻失效
  credentials.invalidate()
  await refresh()
}

async function revokeKey(apiKey: TenantApiKey): Promise<void> {
  const confirmed = await confirmAction({
    title: '撤销 API Key',
    message: '撤销后使用该密钥的业务系统将立即无法发起审批，且不能恢复。确认撤销？',
    submitText: '撤销',
    danger: true,
  })
  if (!confirmed) return
  try {
    await tenantApi.revokeApiKey(tenantId.value, apiKey.id)
    toastOk('API Key 已撤销')
    credentials.invalidate()
    await refresh()
  } catch (err) {
    toastError(errorMessageOf(err))
  }
}

async function revokeCredential(credential: CallbackCredential): Promise<void> {
  const confirmed = await confirmAction({
    title: '撤销回调凭据',
    message: '撤销后审批通过时将无法认证到业务系统，对应执行记录会失败。确认撤销？',
    submitText: '撤销',
    danger: true,
  })
  if (!confirmed) return
  try {
    await tenantApi.revokeCredential(tenantId.value, credential.id)
    toastOk('回调凭据已撤销')
    credentials.invalidate()
    await refresh()
  } catch (err) {
    toastError(errorMessageOf(err))
  }
}

/* ---------------------------------------------------------------------------
   资源授权：这个租户能用哪些审批流与业务动作
   --------------------------------------------------------------------------- */

const grantDialogOpen = ref(false)
const grantDialogMode = ref<'process' | 'action'>('process')

function openGrant(mode: 'process' | 'action'): void {
  grantDialogMode.value = mode
  grantDialogOpen.value = true
}

/**
 * 停用/启用一条授权。停用只影响"以后能不能用"，已经跑起来的审批实例不受影响
 * （后端语义如此，提示里要说清楚，否则没人敢点）。
 */
async function toggleGrant(row: GrantRow, kind: 'process' | 'action'): Promise<void> {
  const disabling = row.status === 'ENABLED'
  if (disabling) {
    const confirmed = await confirmAction({
      title: kind === 'process' ? '停用审批流授权' : '停用业务动作授权',
      message: `停用后这个租户不能再${kind === 'process' ? '用它发起审批' : '触发这个动作'}；已经运行的审批实例不受影响。确认停用？`,
      submitText: '停用',
      danger: true,
    })
    if (!confirmed) return
  }
  try {
    const status = disabling ? 'DISABLED' : 'ENABLED'
    const call =
      kind === 'process'
        ? grantApi.updateProcessBinding(tenantId.value, row.id, status)
        : grantApi.updateActionBinding(tenantId.value, row.id, status)
    await call
    toastOk(disabling ? '授权已停用' : '授权已恢复')
    await refresh()
  } catch (err) {
    toastError(errorMessageOf(err))
  }
}
</script>

<template>
  <template v-if="tenant">
    <Breadcrumb :items="[{ text: '租户', hash: '#/tenants' }, { text: tenant.name }]" />

    <PageHead
      :title="tenant.name"
      :note="`租户编码 ${tenant.code}。密钥和回调凭据属于敏感信息，仅在本页展示。`"
    >
      <ElButton @click="tenantDialogOpen = true">编辑租户</ElButton>
    </PageHead>

    <PanelCard title="基本信息">
      <template #actions>
        <StatusTag :status="tenant.status" />
      </template>
      <KvDescriptions :pairs="basicPairs">
        <template #tenantId>
          <span class="code">{{ tenant.id }}</span>
        </template>
        <template #callbackBaseUrl>
          <span class="code">{{ tenant.callback_base_url }}</span>
        </template>
      </KvDescriptions>
    </PanelCard>

    <PanelCard title="API Key">
      <template #actions>
        <ElButton size="small" type="primary" @click="apiKeyDialogOpen = true">签发密钥</ElButton>
      </template>
      <DataTable
        :columns="apiKeyColumns"
        :rows="apiKeys"
        :loading="loading"
        empty-title="还没有 API Key"
        empty-hint="签发一个密钥交给业务系统，用于调用发起审批接口。"
      >
        <template #cell-api_key="{ row }">
          <template v-if="row.api_key">
            <span class="code">{{ row.api_key }}</span>
            <CopyButton :text="row.api_key" />
          </template>
          <span v-else>—</span>
        </template>
        <template #cell-status="{ row }">
          <StatusTag :status="row.status" />
        </template>
        <template #cell-last_used_at="{ row }">{{ formatTime(row.last_used_at) }}</template>
        <template #cell-expires_at="{ row }">{{ formatTime(row.expires_at) }}</template>
        <template #cell-actions="{ row }">
          <button
            v-if="isActive(row.status)"
            class="btn--link btn--sm is-danger"
            type="button"
            @click="revokeKey(row)"
          >
            撤销
          </button>
          <span v-else class="muted">
            {{ row.revoked_at ? `${formatTime(row.revoked_at)} 已撤销` : '已撤销' }}
          </span>
        </template>
      </DataTable>
    </PanelCard>

    <PanelCard title="回调 Service Token">
      <template #actions>
        <ElButton size="small" @click="credentialDialogOpen = true">配置凭据</ElButton>
      </template>
      <div class="note panel-note">
        审批通过后，审批中心用这里的 Token
        以业务系统认可的方式调用回调接口。只返回元数据，不回显明文。
      </div>
      <DataTable
        :columns="credentialColumns"
        :rows="callbackCredentials"
        :loading="loading"
        empty-title="还没有回调凭据"
        empty-hint="如果业务动作需要调用业务系统接口，必须在这里配置 Service Token。"
      >
        <template #cell-header_name="{ row }">
          <span class="code">{{ headerPreview(row) }}</span>
        </template>
        <template #cell-status="{ row }">
          <StatusTag :status="row.status" />
        </template>
        <template #cell-expires_at="{ row }">{{ formatTime(row.expires_at) }}</template>
        <template #cell-actions="{ row }">
          <button
            v-if="isActive(row.status)"
            class="btn--link btn--sm is-danger"
            type="button"
            @click="revokeCredential(row)"
          >
            撤销
          </button>
          <span v-else class="muted">
            {{ row.revoked_at ? `${formatTime(row.revoked_at)} 已撤销` : '已撤销' }}
          </span>
        </template>
      </DataTable>
    </PanelCard>

    <PanelCard title="审批流授权">
      <template #actions>
        <ElButton size="small" type="primary" @click="openGrant('process')">授权审批流</ElButton>
      </template>
      <DataTable
        :columns="grantColumns"
        :rows="processGrants"
        :loading="loading"
        empty-title="还没有审批流授权"
        empty-hint="授权后业务系统才能用这条流程发起审批。"
      >
        <template #cell-name="{ row }">
          <span class="cell-title">{{ row.name }}</span>
          <StatusTag v-if="row.resourceDisabled" class="inline-tag" status="DISABLED" text="流程已停用" />
        </template>
        <template #cell-resourceShortId="{ row }">
          <span class="code">{{ row.resourceShortId }}</span>
        </template>
        <template #cell-status="{ row }">
          <StatusTag :status="row.status" />
        </template>
        <template #cell-created_at="{ row }">
          <span class="muted">{{ formatTime(row.created_at) }}</span>
        </template>
        <template #cell-actions="{ row }">
          <button class="btn--link btn--sm" type="button" @click="toggleGrant(row, 'process')">
            {{ row.status === 'ENABLED' ? '停用' : '启用' }}
          </button>
        </template>
      </DataTable>
    </PanelCard>

    <PanelCard title="业务动作授权">
      <template #actions>
        <ElButton size="small" type="primary" @click="openGrant('action')">授权业务动作</ElButton>
      </template>
      <DataTable
        :columns="grantColumns"
        :rows="actionGrants"
        :loading="loading"
        empty-title="还没有业务动作授权"
        empty-hint="只有需要审批通过后回调业务系统的租户才需要配置。"
      >
        <template #cell-name="{ row }">
          <span class="cell-title">{{ row.name }}</span>
          <StatusTag v-if="row.resourceDisabled" class="inline-tag" status="DISABLED" text="动作已停用" />
        </template>
        <template #cell-resourceShortId="{ row }">
          <span class="code">{{ row.resourceShortId }}</span>
        </template>
        <template #cell-status="{ row }">
          <StatusTag :status="row.status" />
        </template>
        <template #cell-created_at="{ row }">
          <span class="muted">{{ formatTime(row.created_at) }}</span>
        </template>
        <template #cell-actions="{ row }">
          <button class="btn--link btn--sm" type="button" @click="toggleGrant(row, 'action')">
            {{ row.status === 'ENABLED' ? '停用' : '启用' }}
          </button>
        </template>
      </DataTable>
    </PanelCard>

    <PanelCard title="最近使用记录">
      <template #actions>
        <a class="btn btn--sm" :href="`#/usages?tenant=${tenant.id}`">查看全部</a>
      </template>
      <DataTable
        :columns="usageColumns"
        :rows="usages"
        :loading="loading"
        empty-title="还没有审批记录"
        empty-hint="业务系统使用 API Key 发起审批后，这里会显示记录。"
      >
        <template #cell-created_at="{ row }">{{ formatTime(row.created_at) }}</template>
        <template #cell-approval_title="{ row }">{{ row.approval_title || '—' }}</template>
        <template #cell-business_key="{ row }">
          <span class="code">{{ row.business_key }}</span>
        </template>
        <template #cell-action_code="{ row }">
          <span class="code">{{ row.action_code || '—' }}</span>
        </template>
        <template #cell-approval_status="{ row }">
          <StatusTag :status="row.approval_status || 'ERROR'" />
        </template>
        <template #cell-current_node_name="{ row }">{{ row.current_node_name || '—' }}</template>
        <template #cell-duration_ms="{ row }">{{ formatDuration(row.duration_ms) }}</template>
        <template #cell-actions="{ row }">
          <a class="btn--link btn--sm" :href="instanceHref(row)">查看审批</a>
        </template>
      </DataTable>
    </PanelCard>

    <TenantFormDialog v-model:open="tenantDialogOpen" :tenant="tenant" @saved="afterSaved" />
    <ApiKeyDialog v-model:open="apiKeyDialogOpen" :tenant-id="tenant.id" @saved="afterSaved" />
    <CallbackCredentialDialog
      v-model:open="credentialDialogOpen"
      :tenant-id="tenant.id"
      @saved="afterSaved"
    />
    <GrantBindingDialog
      v-model:open="grantDialogOpen"
      :mode="grantDialogMode"
      :tenant-id="tenant.id"
      :processes="page.processes"
      :actions="page.actions"
      @saved="refresh"
    />
  </template>

  <ErrorPanel v-else-if="error" :error="error" />

  <div v-else class="loading">正在读取数据…</div>
</template>

<style scoped>
/* 凭据表前面那段说明：旧版放在表格上方的独立段落里，这里补一段间距 */
.panel-note {
  margin-bottom: 14px;
}

/* 资源名后面的「已停用」标记，与名字拉开一点距离 */
.inline-tag {
  margin-left: 6px;
}
</style>
