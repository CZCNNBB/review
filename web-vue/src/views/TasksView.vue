<script setup lang="ts">
import { ElButton, ElOption, ElSelect } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { approvalApi } from '@/api/modules/approval'
import type { ApprovalWorkItem, Person } from '@/api/types'
import DataTable from '@/components/common/DataTable.vue'
import type { ColumnSpec } from '@/components/common/DataTable.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import TaskDecisionDialog from '@/components/dialogs/TaskDecisionDialog.vue'
import type { TaskDecisionResult } from '@/components/dialogs/TaskDecisionDialog.vue'
import PersonSelect from '@/components/form/PersonSelect.vue'
import EmptyState from '@/components/layout/EmptyState.vue'
import ErrorPanel from '@/components/layout/ErrorPanel.vue'
import PageHead from '@/components/layout/PageHead.vue'
import PanelCard from '@/components/layout/PanelCard.vue'
import { useAsyncPage } from '@/composables/useAsyncPage'
import { loadPersonDirectory, usePersonDirectory } from '@/composables/usePersonDirectory'
import { useUrlFilters } from '@/composables/useUrlFilters'
import { useShellStore } from '@/stores/shell'
import { formatTime, shortId } from '@/utils/format'
import { toastOk } from '@/utils/notify'
import { statusText } from '@/utils/status'

/** 处理弹窗只需要任务 ID 和所属人员，抄送任务不生成此引用。 */
type TaskActionRef = { id: string; approver_person_id: string }
type WorkKind = 'APPROVAL' | 'COPY'

interface WorkRow {
  id: string
  kind: WorkKind
  title: string
  businessKey: string
  nodeName: string
  personId: string
  personSnapshotName: string
  status: string
  createdAt: string
  detailLink: string
  task?: TaskActionRef
}

interface WorkbenchData {
  persons: Person[]
  rows: WorkRow[]
}

const columns: ColumnSpec[] = [
  { key: 'kind', title: '任务类型', width: 100 },
  { key: 'title', title: '审批单' },
  { key: 'businessKey', title: '业务单号', width: 160 },
  { key: 'nodeName', title: '当前事项', width: 145 },
  { key: 'personId', title: '相关人员', width: 130 },
  { key: 'status', title: '状态', width: 105 },
  { key: 'createdAt', title: '收到时间', width: 170 },
  { key: 'actions', title: '操作', width: 160, align: 'right' },
]

const shell = useShellStore()
const router = useRouter()
const { filter } = useUrlFilters()
const kindFilter = filter('type', 'ALL')
const statusFilter = filter('status', 'ALL')
const personFilter = filter('person')
const directory = usePersonDirectory()
const personOptions = computed(() => [
  { value: '', label: '全部人员' },
  ...directory.options.value,
])

/** 统一接口的任务转为表格行；仅审批类型保留操作引用。 */
function workRow(item: ApprovalWorkItem): WorkRow {
  const isCopy = item.task_type === 'COPY'
  return {
    id: `${isCopy ? 'copy' : 'approval'}-${item.id}`,
    kind: item.task_type,
    title: item.instance_title || '（无标题）',
    businessKey: item.business_key || '—',
    nodeName: item.node_name || (isCopy ? '抄送节点' : '审批节点'),
    personId: item.person_id,
    personSnapshotName: String(item.person_snapshot?.name || ''),
    status: isCopy ? item.instance_status : item.task_status,
    createdAt: item.created_at,
    detailLink: isCopy
      ? `#/copies/${item.id}?person=${encodeURIComponent(item.person_id)}`
      : `#/instances/${item.instance_id}`,
    task: isCopy ? undefined : { id: item.id, approver_person_id: item.person_id },
  }
}

/** 按统一接口的分页大小读取全部任务，避免列表超过一页后被静默截断。 */
async function loadAllWorkItems(): Promise<ApprovalWorkItem[]> {
  const allItems: ApprovalWorkItem[] = []
  const pageSize = 500
  let offset = 0

  while (true) {
    const page = await approvalApi.workItems(offset)
    allItems.push(...page)
    if (page.length < pageSize) return allItems
    offset += pageSize
  }
}

const { data, loading, error, refresh } = useAsyncPage<WorkbenchData>(
  async () => {
    // 人员目录和工作台任务互不依赖，可以同时读取。
    const [personDirectory, items] = await Promise.all([
      loadPersonDirectory(),
      loadAllWorkItems(),
    ])
    const persons = personDirectory.persons
    const rows = items.map(workRow)

    // 导航角标表示真正需要处理的审批待办；抄送无需处理，不计入待办数。
    shell.setCount('workbench', rows.filter((row) => row.task && row.status === 'PENDING').length)
    return { persons, rows }
  },
  { persons: [], rows: [] },
)

/** 三个筛选项在浏览器中筛选同一份已加载列表，切换时不重复请求后端。 */
const visibleRows = computed(() => data.value.rows.filter((row) => {
  if (kindFilter.value !== 'ALL' && row.kind !== kindFilter.value) return false
  if (personFilter.value && row.personId !== personFilter.value) return false
  if (statusFilter.value !== 'ALL' && row.status !== statusFilter.value) return false
  return true
}))

const waitingCount = computed(() => visibleRows.value.filter((row) => row.task && row.status === 'PENDING').length)

/** 优先使用创建任务时保存的姓名快照，以免人员改名后旧记录失去可读性。 */
function personNameOf(row: WorkRow): string {
  return row.personSnapshotName ||
    data.value.persons.find((person) => person.id === row.personId)?.name ||
    shortId(row.personId)
}

const decisionOpen = ref(false)
const decisionKind = ref<'approve' | 'reject'>('approve')
const decisionTask = ref<TaskActionRef | null>(null)
const decisionApproverName = computed(() => {
  const task = decisionTask.value
  if (!task) return '—'
  const row = data.value.rows.find((item) => item.task?.id === task.id)
  return row ? personNameOf(row) : shortId(task.approver_person_id)
})

/** 打开审批操作弹窗；抄送行没有任务对象，因此不会进入本方法。 */
function openDecision(task: TaskActionRef, kind: 'approve' | 'reject'): void {
  decisionKind.value = kind
  decisionTask.value = task
  decisionOpen.value = true
}

/** 审批完成后刷新工作台，并打开对应审批单详情。 */
async function afterDecided(result: TaskDecisionResult): Promise<void> {
  toastOk(
    `已${decisionKind.value === 'approve' ? '同意' : '拒绝'}，审批单当前状态 ${statusText(result.instance_status)}`,
  )
  await refresh()
  if (result.instance_id) void router.push(`/instances/${result.instance_id}`)
}

onMounted(refresh)
</script>

<template>
  <PageHead title="工作台" note="审批任务和抄送记录按收到时间汇总。审批任务可以处理，抄送记录仅供查看。">
    <ElSelect v-model="kindFilter" style="width: 145px">
      <ElOption value="ALL" label="全部类型" />
      <ElOption value="APPROVAL" label="只看审批" />
      <ElOption value="COPY" label="只看抄送" />
    </ElSelect>
    <PersonSelect v-model="personFilter" :options="personOptions" placeholder="全部人员" style="width: 200px" />
    <ElSelect v-model="statusFilter" style="width: 140px">
      <ElOption value="ALL" label="全部状态" />
      <ElOption value="PENDING" label="待办" />
      <ElOption value="APPROVED" label="已通过" />
      <ElOption value="REJECTED" label="已拒绝" />
      <ElOption value="CANCELLED" label="已取消" />
      <ElOption value="RUNNING" label="审批中" />
      <ElOption value="ERROR" label="异常" />
    </ElSelect>
    <ElButton :loading="loading" @click="refresh()">刷新</ElButton>
  </PageHead>

  <ErrorPanel v-if="error" :error="error" />
  <PanelCard v-else-if="!loading && !data.persons.length && !data.rows.length">
    <EmptyState title="还没有工作记录" hint="维护人员并发起审批后，审批任务和抄送记录会出现在这里。">
      <a class="btn btn--sm" href="#/people">去维护人员</a>
    </EmptyState>
  </PanelCard>
  <PanelCard v-else>
    <div v-if="waitingCount" class="note note--work waiting-note">
      当前列表有 {{ waitingCount }} 条审批待办等待处理。
    </div>
    <DataTable
      :columns="columns"
      :rows="visibleRows"
      row-key="id"
      :loading="loading"
      empty-title="没有符合筛选条件的记录"
      empty-hint="可以切换任务类型、人员或状态查看其他记录。"
    >
      <template #cell-kind="{ row }">
        <span class="work-kind" :class="row.kind === 'COPY' ? 'work-kind--copy' : 'work-kind--approval'">
          {{ row.kind === 'COPY' ? '抄送' : '审批' }}
        </span>
      </template>
      <template #cell-title="{ row }">
        <a class="cell-title" :href="row.detailLink">{{ row.title }}</a>
      </template>
      <template #cell-businessKey="{ row }"><span class="code">{{ row.businessKey }}</span></template>
      <template #cell-nodeName="{ row }">{{ row.nodeName }}</template>
      <template #cell-personId="{ row }">{{ personNameOf(row) }}</template>
      <template #cell-status="{ row }"><StatusTag :status="row.status" /></template>
      <template #cell-createdAt="{ row }"><span class="muted">{{ formatTime(row.createdAt) }}</span></template>
      <template #cell-actions="{ row }">
        <template v-if="row.task && row.status === 'PENDING'">
          <button class="btn--link btn--sm" type="button" @click="openDecision(row.task, 'approve')">同意</button>
          <button class="btn--link btn--sm is-danger" type="button" @click="openDecision(row.task, 'reject')">拒绝</button>
        </template>
        <a class="btn--link btn--sm" :href="row.detailLink">{{ row.kind === 'COPY' ? '查看' : '详情' }}</a>
      </template>
    </DataTable>
  </PanelCard>

  <TaskDecisionDialog
    v-model:open="decisionOpen"
    :kind="decisionKind"
    :task="decisionTask"
    :approver-name="decisionApproverName"
    @decided="afterDecided"
  />
</template>

<style scoped>
/* 类型标签在第一列明确区分可处理审批和只读抄送。 */
.work-kind {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 4px;
  border: 1px solid;
  font-weight: 700;
  font-size: 12px;
  letter-spacing: 1px;
}
.work-kind--approval {
  color: var(--indigo);
  background: var(--indigo-wash);
  border-color: #c3d2e4;
}
.work-kind--copy {
  color: #176b62;
  background: #e5f5f1;
  border-color: #9ad3c9;
}
.muted {
  color: var(--ink-3);
}
.cell-title {
  font-weight: 600;
}
.waiting-note {
  margin-bottom: 14px;
}
</style>
