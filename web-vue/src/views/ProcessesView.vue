<script setup lang="ts">
import { ElButton } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { processApi } from '@/api/modules/process'
import type { Process } from '@/api/types'
import DataTable from '@/components/common/DataTable.vue'
import type { ColumnSpec } from '@/components/common/DataTable.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import ProcessFormDialog from '@/components/dialogs/ProcessFormDialog.vue'
import ErrorPanel from '@/components/layout/ErrorPanel.vue'
import PageHead from '@/components/layout/PageHead.vue'
import PanelCard from '@/components/layout/PanelCard.vue'
import { useAsyncPage } from '@/composables/useAsyncPage'
import { confirmAction, errorMessageOf } from '@/composables/useConfirm'
import { useShellStore } from '@/stores/shell'
import { formatTime } from '@/utils/format'
import { toastError, toastOk } from '@/utils/notify'

// 当前版本 / 草稿两列的值是链接，不能走 DataTable 的默认取值，列 key 只当槽位名用
const columns: ColumnSpec[] = [
  { key: 'name', title: '流程名称', width: 200 },
  { key: 'status', title: '状态', width: 90 },
  { key: 'current_version', title: '当前版本', width: 110 },
  { key: 'draft_version', title: '草稿', width: 140 },
  { key: 'node_count', title: '节点数', width: 80, align: 'right' },
  { key: 'updated_at', title: '更新时间', width: 160 },
  { key: 'actions', title: '操作', width: 170, align: 'right' },
]

const router = useRouter()
const shell = useShellStore()

// 解构出来用：模板里 ref 会自动解包，不必到处写 .value
const {
  data: processes,
  loading,
  error,
  refresh,
} = useAsyncPage(async () => {
  const list = await processApi.processes(200)
  shell.setCount('processes', list.length)
  return list
}, [] as Process[])

const dialogOpen = ref(false)

function openCreate(): void {
  dialogOpen.value = true
}

function afterCreated(created: Process): void {
  // 旧版建完直接进 V1 草稿的编排页；接口没给草稿才退回流程详情
  router.push(
    created.draft_version_id ? `/versions/${created.draft_version_id}` : `/processes/${created.id}`,
  )
}

async function createDraft(row: Process): Promise<void> {
  try {
    const version = await processApi.createDraft(row.id)
    toastOk(`已创建 V${version.version_no} 草稿`)
    router.push(`/versions/${version.id}`)
  } catch (err) {
    toastError(errorMessageOf(err))
  }
}

async function copyProcess(row: Process): Promise<void> {
  const confirmed = await confirmAction({
    title: '复制审批流',
    message: '将复制当前可见版本，生成一条拥有 V1 草稿的新流程。确认复制？',
    submitText: '复制',
  })
  if (!confirmed) return
  try {
    const copied = await processApi.copy(row.id)
    toastOk('审批流已复制')
    router.push(`/processes/${copied.id}`)
  } catch (err) {
    toastError(errorMessageOf(err))
  }
}

async function disableProcess(row: Process): Promise<void> {
  const confirmed = await confirmAction({
    title: '停用审批流',
    message: '停用后业务系统不能再使用该流程发起新审批，已经运行的实例不受影响。确认停用？',
    submitText: '停用',
    danger: true,
  })
  if (!confirmed) return
  try {
    await processApi.disable(row.id)
    toastOk('审批流已停用')
    await refresh()
  } catch (err) {
    toastError(errorMessageOf(err))
  }
}

onMounted(refresh)
</script>

<template>
  <PageHead
    title="审批流"
    note="流程的稳定身份与版本分离：已发布版本永久只读，编辑时先创建下一版草稿，发布后原子切换为新版本。"
  >
    <ElButton type="primary" @click="openCreate">新建审批流</ElButton>
  </PageHead>

  <ErrorPanel v-if="error" :error="error" />

  <PanelCard v-else>
    <DataTable
      :columns="columns"
      :rows="processes"
      :loading="loading"
      empty-title="还没有审批流"
      empty-hint="新建审批流后会同步生成 V1 草稿，接着配置节点、审批人和分支条件。"
    >
      <template #cell-name="{ row }">
        <a class="cell-title" :href="`#/processes/${row.id}`">{{ row.name }}</a>
      </template>
      <template #cell-status="{ row }">
        <StatusTag :status="row.status" />
      </template>
      <template #cell-current_version="{ row }">
        <a
          v-if="row.current_version_id"
          class="code"
          :href="`#/versions/${row.current_version_id}`"
        >
          V{{ row.current_version_no }}
        </a>
        <span v-else class="muted">未发布</span>
      </template>
      <template #cell-draft_version="{ row }">
        <a v-if="row.draft_version_id" class="code" :href="`#/versions/${row.draft_version_id}`">
          V{{ row.draft_version_no }} 编辑中
        </a>
        <button v-else class="btn--link btn--sm" type="button" @click="createDraft(row)">
          创建草稿
        </button>
      </template>
      <template #cell-updated_at="{ row }">
        <span class="muted">{{ formatTime(row.updated_at) }}</span>
      </template>
      <template #cell-actions="{ row }">
        <a class="btn--link btn--sm" :href="`#/processes/${row.id}`">详情</a>
        <button class="btn--link btn--sm" type="button" @click="copyProcess(row)">复制</button>
        <button
          v-if="row.status !== 'DISABLED'"
          class="btn--link btn--sm is-danger"
          type="button"
          @click="disableProcess(row)"
        >
          停用
        </button>
      </template>
      <template #empty-action>
        <ElButton type="primary" size="small" @click="openCreate">新建审批流</ElButton>
      </template>
    </DataTable>
  </PanelCard>

  <ProcessFormDialog v-model:open="dialogOpen" @saved="afterCreated" />
</template>

<style scoped>
/* 旧版的 .muted / .cell-title 挂在 .tbl 下，AntD 表格里继承不到，按同一套令牌补一份 */
.muted {
  color: var(--ink-3);
}
.cell-title {
  font-weight: 600;
}
</style>
