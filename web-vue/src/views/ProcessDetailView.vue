<script setup lang="ts">
import { ElButton } from 'element-plus'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { processApi } from '@/api/modules/process'
import type { Process, ProcessVersion } from '@/api/types'
import DataTable from '@/components/common/DataTable.vue'
import type { ColumnSpec } from '@/components/common/DataTable.vue'
import IssuesDialog from '@/components/common/IssuesDialog.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import Breadcrumb from '@/components/layout/Breadcrumb.vue'
import ErrorPanel from '@/components/layout/ErrorPanel.vue'
import KvDescriptions from '@/components/layout/KvDescriptions.vue'
import PageHead from '@/components/layout/PageHead.vue'
import PanelCard from '@/components/layout/PanelCard.vue'
import { useAsyncPage } from '@/composables/useAsyncPage'
import { confirmAction, errorMessageOf } from '@/composables/useConfirm'
import type { ValidationIssue } from '@/types/domain'
import { formatTime } from '@/utils/format'
import { toastError, toastOk } from '@/utils/notify'

const columns: ColumnSpec[] = [
  { key: 'version_no', title: '版本', width: 80 },
  { key: 'name', title: '名称', width: 180 },
  { key: 'status', title: '状态', width: 90 },
  { key: 'node_count', title: '节点数', width: 80, align: 'right' },
  { key: 'revision', title: '修订号', width: 80, align: 'right' },
  { key: 'published_at', title: '发布时间', width: 160 },
  { key: 'actions', title: '操作', width: 170, align: 'right' },
]

const route = useRoute()
const router = useRouter()

const processId = computed(() => String(route.params.id ?? ''))

// 流程与版本历史一起等：整页只呈现一份数据，避免两块内容各显示各的加载态
const { data, loading, error, refresh } = useAsyncPage(
  async () => {
    const [process, versions] = await Promise.all([
      processApi.get(processId.value),
      processApi.versions(processId.value),
    ])
    return { process, versions }
  },
  { process: null as Process | null, versions: [] as ProcessVersion[] },
)

const process = computed(() => data.value.process)
const versions = computed(() => data.value.versions)

// 概况里的值要放等宽字与次要色，交给 KvDescriptions 的具名插槽渲染
const overviewPairs = computed(() => [
  { key: '流程 ID', slot: 'id' },
  { key: '当前版本', slot: 'current-version' },
  { key: '编辑中草稿', slot: 'draft-version' },
  { key: '当前版本节点数', slot: 'node-count' },
  { key: '更新时间', value: formatTime(process.value?.updated_at) },
])

const issuesOpen = ref(false)
const issuesTitle = ref('校验未通过')
const issues = ref<ValidationIssue[]>([])

async function createDraft(): Promise<void> {
  const current = process.value
  if (!current) return
  try {
    const version = await processApi.createDraft(current.id)
    toastOk(`已创建 V${version.version_no} 草稿`)
    await refresh()
  } catch (err) {
    toastError(errorMessageOf(err))
  }
}

async function copyProcess(): Promise<void> {
  const current = process.value
  if (!current) return
  try {
    const copied = await processApi.copy(current.id)
    toastOk('审批流已复制')
    router.push(`/processes/${copied.id}`)
  } catch (err) {
    toastError(errorMessageOf(err))
  }
}

async function validateVersion(version: ProcessVersion): Promise<void> {
  try {
    const result = await processApi.validate(version.id)
    if (result.valid) {
      toastOk('校验通过，可以发布')
      return
    }
    issues.value = result.issues
    issuesTitle.value = '校验未通过'
    issuesOpen.value = true
  } catch (err) {
    toastError(errorMessageOf(err))
  }
}

async function publishVersion(version: ProcessVersion): Promise<void> {
  const confirmed = await confirmAction({
    title: '发布版本',
    message: '发布会执行完整校验并把该版本切换为流程当前版本，已发布版本之后不可修改。确认发布？',
    submitText: '发布',
  })
  if (!confirmed) return
  try {
    await processApi.publish(version.id)
    toastOk('版本已发布')
    await refresh()
  } catch (err) {
    // 校验不过或版本已被改过都会走到这里，后端的话直接呈现给用户
    toastError(errorMessageOf(err))
  }
}

// 直接改地址换流程（例如从别处粘贴链接）时也要重新取数
watch(processId, refresh, { immediate: true })
</script>

<template>
  <ErrorPanel v-if="error" :error="error" />

  <template v-else-if="process">
    <Breadcrumb :items="[{ text: '审批流', hash: '#/processes' }, { text: process.name }]" />

    <PageHead :title="process.name" :note="process.description || '暂无流程说明'">
      <!-- 旧版「继续编辑」是链接，这里统一成按钮：跳到编辑器是导航，不是动作 -->
      <ElButton
        v-if="process.draft_version_id"
        type="primary"
        @click="router.push(`/versions/${process.draft_version_id}`)"
      >
        继续编辑 V{{ process.draft_version_no }}
      </ElButton>
      <ElButton v-else type="primary" @click="createDraft">创建下一版草稿</ElButton>
      <ElButton @click="copyProcess">复制流程</ElButton>
    </PageHead>

    <PanelCard title="流程概况">
      <template #actions>
        <StatusTag :status="process.status" />
      </template>
      <KvDescriptions :pairs="overviewPairs">
        <template #id>
          <span class="code">{{ process.id }}</span>
        </template>
        <template #current-version>
          <span v-if="process.current_version_id">V{{ process.current_version_no }}</span>
          <span v-else class="muted">未发布</span>
        </template>
        <template #draft-version>
          <span v-if="process.draft_version_id">V{{ process.draft_version_no }}</span>
          <span v-else class="muted">无</span>
        </template>
        <template #node-count>
          <span class="code">{{ process.node_count }}</span>
        </template>
      </KvDescriptions>
      <div v-if="!process.draft_version_id" class="note overview-note">
        当前没有草稿。需要修改流程时，点“创建下一版草稿”从当前发布版本复制一份。
      </div>
    </PanelCard>

    <PanelCard title="版本历史">
      <template #header>
        <span class="panel__note">已发布版本只读，用于追溯和对比；新实例始终使用当前版本</span>
      </template>
      <DataTable
        :columns="columns"
        :rows="versions"
        :loading="loading"
        empty-title="暂无版本"
        empty-hint="正常情况下新建流程时会自动创建 V1 草稿。"
      >
        <template #cell-version_no="{ row }">
          <span class="cell-title">V{{ row.version_no }}</span>
        </template>
        <template #cell-status="{ row }">
          <StatusTag :status="row.status" />
        </template>
        <template #cell-published_at="{ row }">
          <span class="muted">{{ formatTime(row.published_at) }}</span>
        </template>
        <template #cell-actions="{ row }">
          <a class="btn--link btn--sm" :href="`#/versions/${row.id}`">
            {{ row.status === 'DRAFT' ? '编辑' : '查看' }}
          </a>
          <button class="btn--link btn--sm" type="button" @click="validateVersion(row)">
            校验
          </button>
          <button
            v-if="row.status === 'DRAFT'"
            class="btn--link btn--sm"
            type="button"
            @click="publishVersion(row)"
          >
            发布
          </button>
        </template>
      </DataTable>
    </PanelCard>
  </template>

  <IssuesDialog v-model:open="issuesOpen" :title="issuesTitle" :issues="issues" />
</template>

<style scoped>
/* 旧版的 .muted / .cell-title 挂在 .tbl 下，AntD 表格里继承不到，按同一套令牌补一份 */
.muted {
  color: var(--ink-3);
}
.cell-title {
  font-weight: 600;
}
.overview-note {
  margin-top: 14px;
}
</style>
