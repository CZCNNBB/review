<script setup lang="ts">
import { ElButton, ElInput, ElOption, ElSelect } from 'element-plus'
import { onMounted, ref, watch } from 'vue'

import { safe } from '@/api/http'
import { tenantApi } from '@/api/modules/tenant'
import type { ProcessUsageRecord, Tenant } from '@/api/types'
import DataTable from '@/components/common/DataTable.vue'
import type { ColumnSpec } from '@/components/common/DataTable.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import EmptyState from '@/components/layout/EmptyState.vue'
import ErrorPanel from '@/components/layout/ErrorPanel.vue'
import PageHead from '@/components/layout/PageHead.vue'
import PanelCard from '@/components/layout/PanelCard.vue'
import { useAsyncPage } from '@/composables/useAsyncPage'
import { useUrlFilters } from '@/composables/useUrlFilters'
import { useCredentialsStore } from '@/stores/credentials'
import { useShellStore } from '@/stores/shell'
import { formatDuration, formatTime } from '@/utils/format'

/** 使用记录接口按租户提供，合并成一张全量表时租户名/编码要自己带上（旧版同此） */
type UsageRow = ProcessUsageRecord & { tenant_name: string; tenant_code: string }

interface UsagesData {
  tenants: Tenant[]
  records: UsageRow[]
}

const columns: ColumnSpec[] = [
  { key: 'created_at', title: '发起时间', width: 160 },
  { key: 'tenant_name', title: '租户', width: 150 },
  { key: 'approval_title', title: '审批单' },
  { key: 'business_key', title: '业务单号', width: 180 },
  { key: 'action_code', title: '业务动作', width: 150 },
  { key: 'approval_status', title: '审批状态', width: 100 },
  { key: 'current_node_name', title: '当前节点', width: 150 },
  { key: 'duration_ms', title: '耗时', width: 100, align: 'right' },
  { key: 'actions', title: '操作', width: 110, align: 'right' },
]

const shell = useShellStore()
const credentials = useCredentialsStore()
const filters = useUrlFilters()

// 两个条件都是「点查询才生效」的（旧版从输入框现读现拼），所以页面里留一份草稿，
// 地址栏只保留已生效的那份
const tenantFilter = filters.filter('tenant')
const businessKeyFilter = filters.filter('business_key')
const tenantDraft = ref(tenantFilter.value)
const businessKeyDraft = ref(businessKeyFilter.value)

function search(): void {
  filters.write({ tenant: tenantDraft.value, business_key: businessKeyDraft.value.trim() })
}

function reset(): void {
  tenantDraft.value = ''
  businessKeyDraft.value = ''
  filters.write({ tenant: null, business_key: null })
}

const { data, loading, error, refresh } = useAsyncPage<UsagesData>(
  async () => {
    // 租户列表拉不到时这张表无从谈起，这一项不兜底，交给整页错误面板（旧版同样如此）
    const tenants = await credentials.loadTenants()
    // URL 里的租户取不到（链接指向已删租户）时按「全部租户」处理，否则会得到一张
    // 看起来「没有任何记录」的空表，和筛选行显示的租户自相矛盾（与旧的资源授权页同一条取舍）
    const picked = tenants.find((item) => item.id === tenantFilter.value)
    const targets = picked ? [picked] : tenants

    // 旧版策略原样保留：按租户扇出查询再合并成一张全量表
    const groups = await Promise.all(
      targets.map((tenant) =>
        safe(
          tenantApi.usageRecords(tenant.id, 200, businessKeyFilter.value || undefined),
          [] as ProcessUsageRecord[],
        ),
      ),
    )
    const records = groups
      .flatMap((list, index) =>
        list.map((record) => ({
          ...record,
          tenant_name: targets[index].name,
          tenant_code: targets[index].code,
        })),
      )
      .sort(
        (left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
      )

    shell.setCount('usages', records.length)
    return { tenants, records }
  },
  { tenants: [] as Tenant[], records: [] as UsageRow[] },
)

// 生效的筛选条件只在地址栏存一份：查询、刷新、后退、把链接发给别人，看到的都是同一份结果。
// 草稿跟着回填，否则后退回上一步条件时，输入框与表格会各说各话（旧版整体重渲染没有这个问题）
watch([tenantFilter, businessKeyFilter], () => {
  tenantDraft.value = tenantFilter.value
  businessKeyDraft.value = businessKeyFilter.value
  void refresh()
})

onMounted(refresh)
</script>

<template>
  <PageHead
    title="使用记录"
    note="全部租户的审批发起记录合并展示，按发起时间倒序。审批状态和当前节点在查询时从运行表实时读取。"
  />

  <ErrorPanel v-if="error" :error="error" />

  <PanelCard v-else-if="loading && !data.tenants.length">
    <div class="loading">正在读取数据…</div>
  </PanelCard>

  <PanelCard v-else-if="!data.tenants.length">
    <EmptyState title="还没有租户" hint="业务系统接入后，这里会显示审批使用记录。" />
  </PanelCard>

  <PanelCard v-else>
    <div class="filters-row">
      <div class="field">
        <label class="field__label">租户</label>
        <ElSelect v-model="tenantDraft" style="width: 200px">
          <ElOption value="" label="全部租户" />
          <ElOption
            v-for="tenant in data.tenants"
            :key="tenant.id"
            :value="tenant.id"
            :label="tenant.name"
          />
        </ElSelect>
      </div>
      <div class="field">
        <label class="field__label">业务单号</label>
        <ElInput v-model="businessKeyDraft" placeholder="按单号精确查询" style="width: 220px" />
      </div>
      <ElButton type="primary" size="small" @click="search">查询</ElButton>
      <ElButton v-if="tenantFilter || businessKeyFilter" size="small" @click="reset">
        清空条件
      </ElButton>
    </div>

    <DataTable
      :columns="columns"
      :rows="data.records"
      :loading="loading"
      empty-title="没有使用记录"
      empty-hint="业务系统用租户 API Key 发起审批后，这里会产生记录。"
    >
      <template #cell-created_at="{ row }">
        <span class="muted">{{ formatTime(row.created_at) }}</span>
      </template>
      <template #cell-tenant_name="{ row }">
        <span class="cell-title">{{ row.tenant_name }}</span>
        <div class="muted code">{{ row.tenant_code }}</div>
      </template>
      <template #cell-approval_title="{ row }">
        <a class="cell-title" :href="`#/instances/${row.approval_instance_id}`">
          {{ row.approval_title || '—' }}
        </a>
      </template>
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
        <a class="btn--link btn--sm" :href="`#/instances/${row.approval_instance_id}`">
          查看审批
        </a>
      </template>
    </DataTable>
  </PanelCard>
</template>

<style scoped>
/* 筛选行：旧版是整条 .filters 带（自带 padding 与底色），放进 PanelCard 的 body 里
   会多一层内边距，所以这里只保留排版（与人员与部门页同一条取舍） */
.filters-row {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

/* 旧版的 .muted / .cell-title 只写在 .tbl 作用域里，AntD 表格匹配不到，各补一条 */
.muted {
  color: var(--ink-3);
}
.cell-title {
  font-weight: 600;
}
</style>
