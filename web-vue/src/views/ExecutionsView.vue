<script setup lang="ts">
import { ElOption, ElSelect } from 'element-plus'
import { onMounted, watch } from 'vue'

import { actionApi } from '@/api/modules/action'
import type { ExecutionRecord } from '@/api/types'
import DataTable from '@/components/common/DataTable.vue'
import type { ColumnSpec } from '@/components/common/DataTable.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import ErrorPanel from '@/components/layout/ErrorPanel.vue'
import PageHead from '@/components/layout/PageHead.vue'
import PanelCard from '@/components/layout/PanelCard.vue'
import { useAsyncPage } from '@/composables/useAsyncPage'
import { useUrlFilters } from '@/composables/useUrlFilters'
import { useShellStore } from '@/stores/shell'
import { formatDuration, formatTime } from '@/utils/format'
import { statusText } from '@/utils/status'

/** 执行记录的四种终态。筛选值走地址栏，选项文案统一取 STATUS_TEXT。 */
const STATUSES = ['PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED']

/** 失败原因在列表里只截 60 字，完整内容进详情页 */
const ERROR_PREVIEW_LENGTH = 60

const columns: ColumnSpec[] = [
  { key: 'created_at', title: '创建时间', width: 160 },
  { key: 'action_code', title: '业务动作', width: 180 },
  { key: 'call', title: '调用' },
  { key: 'status', title: '执行状态', width: 100 },
  { key: 'http_status_code', title: 'HTTP', width: 90, align: 'right' },
  { key: 'duration_ms', title: '耗时', width: 110, align: 'right' },
  { key: 'error_message', title: '失败原因' },
  { key: 'actions', title: '操作', width: 90, align: 'right' },
]

const shell = useShellStore()
const statusFilter = useUrlFilters().filter('status')

const {
  data: records,
  loading,
  error,
  refresh,
} = useAsyncPage(async () => {
  const list = await actionApi.executionRecords({
    limit: 200,
    status: statusFilter.value || undefined,
  })
  shell.setCount('executions', list.length)
  return list
}, [] as ExecutionRecord[])

// 筛选条件只在地址栏存一份：刷新、后退、把链接发给别人，看到的都是同一份结果
watch(statusFilter, () => void refresh())

onMounted(refresh)
</script>

<template>
  <PageHead
    title="执行记录"
    note="审批通过后由后台 Worker 调用业务系统。第一版不自动重试，失败记录保留原因供人工核对。列表不返回响应正文和 Service Token。"
  >
    <ElSelect v-model="statusFilter" style="width: 160px">
      <ElOption value="" label="全部状态" />
      <ElOption
        v-for="status in STATUSES"
        :key="status"
        :value="status"
        :label="statusText(status)"
      />
    </ElSelect>
  </PageHead>

  <ErrorPanel v-if="error" :error="error" />

  <PanelCard v-else>
    <DataTable
      :columns="columns"
      :rows="records"
      :loading="loading"
      empty-title="还没有执行记录"
      empty-hint="审批通过且配置了业务动作时，会在这里生成一条调用记录。"
    >
      <template #cell-created_at="{ row }">
        <span class="muted">{{ formatTime(row.created_at) }}</span>
      </template>
      <template #cell-action_code="{ row }">
        <span class="code">{{ row.action_code }}</span>
      </template>
      <template #cell-call="{ row }">
        <span class="code">{{ row.http_method || '—' }} {{ row.relative_path || '' }}</span>
      </template>
      <template #cell-status="{ row }">
        <StatusTag :status="row.status" />
      </template>
      <template #cell-duration_ms="{ row }">{{ formatDuration(row.duration_ms) }}</template>
      <template #cell-error_message="{ row }">
        <span v-if="row.error_message" class="is-error">
          {{ row.error_message.slice(0, ERROR_PREVIEW_LENGTH) }}
        </span>
        <span v-else class="muted">—</span>
      </template>
      <template #cell-actions="{ row }">
        <a class="btn--link btn--sm" :href="`#/executions/${row.id}`">详情</a>
      </template>
    </DataTable>
  </PanelCard>
</template>

<style scoped>
/* 旧版 .muted / 朱砂色失败原因只写在 .tbl 作用域里，AntD 表格匹配不到，各补一条 */
.muted {
  color: var(--ink-3);
}
.is-error {
  color: var(--cinnabar);
}
</style>
