<script setup lang="ts">
import { ElButton } from 'element-plus'
import { onMounted, ref } from 'vue'

import { actionApi } from '@/api/modules/action'
import type { BusinessAction } from '@/api/types'
import DataTable from '@/components/common/DataTable.vue'
import type { ColumnSpec } from '@/components/common/DataTable.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import BusinessActionDialog from '@/components/dialogs/BusinessActionDialog.vue'
import ErrorPanel from '@/components/layout/ErrorPanel.vue'
import PageHead from '@/components/layout/PageHead.vue'
import PanelCard from '@/components/layout/PanelCard.vue'
import { useAsyncPage } from '@/composables/useAsyncPage'
import { useShellStore } from '@/stores/shell'

const columns: ColumnSpec[] = [
  { key: 'action_code', title: '动作标识', width: 200 },
  { key: 'name', title: '名称', width: 160 },
  { key: 'http_method', title: '调用' },
  { key: 'success_status_codes', title: '成功状态码', width: 130 },
  { key: 'timeout_ms', title: '超时', width: 100, align: 'right' },
  { key: 'status', title: '状态', width: 90 },
  { key: 'actions', title: '操作', width: 80, align: 'right' },
]

const shell = useShellStore()

const {
  data: actions,
  loading,
  error,
  refresh,
} = useAsyncPage(async () => {
  const list = await actionApi.list(200)
  shell.setCount('actions', list.length)
  return list
}, [] as BusinessAction[])

const dialogOpen = ref(false)
const editing = ref<BusinessAction | null>(null)

function openCreate(): void {
  editing.value = null
  dialogOpen.value = true
}

function openEdit(action: BusinessAction): void {
  editing.value = action
  dialogOpen.value = true
}

async function afterSaved(): Promise<void> {
  await refresh()
}

onMounted(refresh)
</script>

<template>
  <PageHead
    title="业务动作"
    note="业务动作描述审批通过后要调用的业务接口。实际请求地址由租户的回调基础地址加相对路径组成，认证使用租户配置的 Service Token。"
  >
    <ElButton type="primary" @click="openCreate">新建业务动作</ElButton>
  </PageHead>

  <ErrorPanel v-if="error" :error="error" />

  <PanelCard v-else>
    <DataTable
      :columns="columns"
      :rows="actions"
      :loading="loading"
      empty-title="还没有业务动作"
      empty-hint="如果审批通过后不需要回调业务系统，可以跳过这一步。"
    >
      <template #cell-action_code="{ row }">
        <span class="cell-title code">{{ row.action_code }}</span>
      </template>
      <template #cell-http_method="{ row }">
        <span class="code">{{ row.http_method }} {{ row.relative_path }}</span>
      </template>
      <template #cell-success_status_codes="{ row }">
        <!-- 留空表示不挑状态码，全部 2xx 都算成功 -->
        <span class="code">
          {{
            (row.success_status_codes || []).length
              ? row.success_status_codes.join(', ')
              : '全部 2xx'
          }}
        </span>
      </template>
      <template #cell-timeout_ms="{ row }">
        <span class="code">{{ row.timeout_ms }} ms</span>
      </template>
      <template #cell-status="{ row }">
        <StatusTag :status="row.status" />
      </template>
      <template #cell-actions="{ row }">
        <button class="btn--link btn--sm" type="button" @click="openEdit(row)">编辑</button>
      </template>
      <template #empty-action>
        <ElButton type="primary" size="small" @click="openCreate">新建业务动作</ElButton>
      </template>
    </DataTable>
  </PanelCard>

  <BusinessActionDialog v-model:open="dialogOpen" :action="editing" @saved="afterSaved" />
</template>

<style scoped>
/* 旧版的 .cell-title 只写在 .tbl 作用域里，AntD 的表格里匹配不到，这里补一条 */
.cell-title {
  font-weight: 600;
}
</style>
