<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'

import { approvalApi } from '@/api/modules/approval'
import type { ApprovalCopy, Person } from '@/api/types'
import DataTable from '@/components/common/DataTable.vue'
import type { ColumnSpec } from '@/components/common/DataTable.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import PersonSelect from '@/components/form/PersonSelect.vue'
import ErrorPanel from '@/components/layout/ErrorPanel.vue'
import PageHead from '@/components/layout/PageHead.vue'
import PanelCard from '@/components/layout/PanelCard.vue'
import { useAsyncPage } from '@/composables/useAsyncPage'
import { loadPersonDirectory, usePersonDirectory } from '@/composables/usePersonDirectory'
import { useUrlFilters } from '@/composables/useUrlFilters'
import { formatTime } from '@/utils/format'

interface CopiesPageData {
  persons: Person[]
  copies: ApprovalCopy[]
}

const columns: ColumnSpec[] = [
  { key: 'instance_title', title: '审批单' },
  { key: 'business_key', title: '业务单号', width: 170 },
  { key: 'node_name', title: '抄送节点', width: 140 },
  { key: 'recipient_person_id', title: '抄送人', width: 130 },
  { key: 'instance_status', title: '审批状态', width: 110 },
  { key: 'created_at', title: '抄送时间', width: 170 },
]

const { filter } = useUrlFilters()
const personFilter = filter('person')
const directory = usePersonDirectory()
const personOptions = computed(() => [
  { value: '', label: '全部抄送记录' },
  ...directory.options.value,
])

const { data, loading, error, refresh } = useAsyncPage<CopiesPageData>(
  async () => {
    const persons = (await loadPersonDirectory()).persons
    // 无筛选时直接读取全量抄送记录；链接中的人员无效时也回到全量列表。
    const selected = persons.find((person) => person.id === personFilter.value)
    const copies = await approvalApi.copies(selected?.id)
    return { persons, copies }
  },
  { persons: [], copies: [] },
)

/** 把收件人 ID 转为当前人员目录中的姓名。 */
function personNameOf(personId: string): string {
  return data.value.persons.find((person) => person.id === personId)?.name || personId
}

/** 构造保留收件人身份的只读详情链接。 */
function detailLink(copy: ApprovalCopy): string {
  return `#/copies/${copy.id}?person=${encodeURIComponent(copy.recipient_person_id)}`
}

watch(personFilter, () => void refresh())
onMounted(refresh)
</script>

<template>
  <PageHead title="抄送记录" note="流程走到抄送节点时，审批单会出现在指定人员的列表中；抄送不需要审批操作。">
    <PersonSelect
      v-model="personFilter"
      :options="personOptions"
      placeholder="全部抄送记录"
      style="width: 220px"
    />
  </PageHead>

  <ErrorPanel v-if="error" :error="error" />
  <PanelCard v-else>
    <DataTable
      :columns="columns"
      :rows="data.copies"
      :loading="loading"
      empty-title="暂无抄送审批单"
      empty-hint="流程走到抄送节点后，审批单会出现在这里。"
    >
      <template #cell-instance_title="{ row }">
        <a class="cell-title" :href="detailLink(row)">{{ row.instance_title }}</a>
      </template>
      <template #cell-business_key="{ row }">{{ row.business_key }}</template>
      <template #cell-node_name="{ row }">{{ row.node_name }}</template>
      <template #cell-recipient_person_id="{ row }">
        {{ personNameOf(row.recipient_person_id) }}
      </template>
      <template #cell-instance_status="{ row }">
        <StatusTag :status="row.instance_status" />
      </template>
      <template #cell-created_at="{ row }">{{ formatTime(row.created_at) }}</template>
    </DataTable>
  </PanelCard>
</template>

<style scoped>
.cell-title {
  font-weight: 600;
}
</style>
