<script setup lang="ts">
import { ElOption, ElSelect } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { safe } from '@/api/http'
import { approvalApi } from '@/api/modules/approval'
import { orgApi } from '@/api/modules/org'
import type { ApprovalTask, Person } from '@/api/types'
import DataTable from '@/components/common/DataTable.vue'
import type { ColumnSpec } from '@/components/common/DataTable.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import TaskDecisionDialog from '@/components/dialogs/TaskDecisionDialog.vue'
import type { TaskDecisionResult } from '@/components/dialogs/TaskDecisionDialog.vue'
import EmptyState from '@/components/layout/EmptyState.vue'
import ErrorPanel from '@/components/layout/ErrorPanel.vue'
import PageHead from '@/components/layout/PageHead.vue'
import PanelCard from '@/components/layout/PanelCard.vue'
import { useAsyncPage } from '@/composables/useAsyncPage'
import { useUrlFilters } from '@/composables/useUrlFilters'
import { useShellStore } from '@/stores/shell'
import { formatDuration, formatTime, shortId } from '@/utils/format'
import { toastOk } from '@/utils/notify'
import { statusText } from '@/utils/status'

/** 任务列表里还有 duration_ms（「停留时长」列要用），共享类型没写，本地补上。 */
type TaskRow = ApprovalTask & { duration_ms?: number | null }

interface TasksData {
  persons: Person[]
  tasks: TaskRow[]
}

const columns: ColumnSpec[] = [
  { key: 'instance_title', title: '审批单' },
  { key: 'business_key', title: '业务单号', width: 170 },
  { key: 'node_name', title: '节点', width: 150 },
  { key: 'approver_person_id', title: '审批人', width: 130 },
  { key: 'status', title: '任务状态', width: 100 },
  { key: 'created_at', title: '产生时间', width: 160 },
  { key: 'duration_ms', title: '停留时长', width: 120, align: 'right' },
  { key: 'actions', title: '操作', width: 160, align: 'right' },
]

const shell = useShellStore()
const router = useRouter()

// 筛选条件只认地址栏那一份：刷新、后退、把链接发给别人，看到的都是同一份结果
const { filter } = useUrlFilters()
const statusFilter = filter('status', 'PENDING')
const personFilter = filter('person')

const { data, loading, error, refresh } = useAsyncPage<TasksData>(
  async () => {
    // 人员是整页的前提（没有人员就没有审批人），这一项不兜底，失败交给错误面板
    const persons = await orgApi.persons(200)
    if (!persons.length) {
      shell.setCount('tasks', 0)
      return { persons, tasks: [] }
    }

    // 任务查询只有人员维度，管理台在这里扇出到每个人员再合并，得到全量视图（旧版策略，保持）。
    // 地址栏里的审批人取不到（人员被删或链接写错）时按「全部审批人」处理，避免得到一张
    // 看起来没有任何任务、却和页头下拉显示不一致的空表。
    const picked = persons.find((person) => person.id === personFilter.value)
    const targets = personFilter.value && picked ? [picked] : persons
    // 「全部状态」就是不传 status，旧版同样把 ALL 变成不带筛选条件
    const status = statusFilter.value === 'ALL' ? undefined : statusFilter.value

    const groups = await Promise.all(
      // 单个人员的查询失败只让那部分任务缺失，不该把整页变成错误面板
      targets.map((person) => safe(approvalApi.tasks(person.id, status), [] as TaskRow[])),
    )
    const tasks = groups
      .flat()
      .sort(
        (left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
      )

    shell.setCount('tasks', tasks.length)
    return { persons, tasks }
  },
  { persons: [], tasks: [] },
)

/** 待办数只在「只看待办」这一档下提示，与表格里的内容对得上（旧版同此）。 */
const waiting = computed(() => data.value.tasks.filter((task) => task.status === 'PENDING'))
const showWaitingNote = computed(() => statusFilter.value === 'PENDING' && waiting.value.length > 0)

const emptyTitle = computed(() =>
  statusFilter.value === 'PENDING' ? '没有待办任务' : '没有审批记录',
)
const emptyHint = computed(() =>
  statusFilter.value === 'PENDING'
    ? '业务系统发起审批后，分配给审批人的任务会出现在这里。'
    : '处理过任务后，记录会保留在这里。',
)

// 换筛选条件只是一次新查询：不在页面里另存一份状态
watch([statusFilter, personFilter], () => void refresh())

function personNameOf(personId?: string | null): string {
  const person = data.value.persons.find((item) => item.id === personId)
  return person ? person.name : shortId(personId)
}

/* ---------------------------------------------------------------------------
   处理任务：同意 / 拒绝共用 TaskDecisionDialog
   --------------------------------------------------------------------------- */

const decisionOpen = ref(false)
const decisionKind = ref<'approve' | 'reject'>('approve')
const decisionTask = ref<TaskRow | null>(null)

const decisionApproverName = computed(() => personNameOf(decisionTask.value?.approver_person_id))

function openDecision(task: TaskRow, kind: 'approve' | 'reject'): void {
  decisionKind.value = kind
  decisionTask.value = task
  decisionOpen.value = true
}

async function afterDecided(result: TaskDecisionResult): Promise<void> {
  toastOk(
    `已${decisionKind.value === 'approve' ? '同意' : '拒绝'}，审批单当前状态 ${statusText(result.instance_status)}`,
  )
  // 旧版：拿到审批单就跳详情，拿不到（接口没回 instance_id）就留在列表上刷新
  if (result.instance_id) void router.push(`/instances/${result.instance_id}`)
  else await refresh()
}

onMounted(refresh)
</script>

<template>
  <PageHead
    title="审批任务"
    note="全部审批人的任务集中在这里，按产生时间倒序。管理台代为处理时使用任务所属审批人的身份，用于联调和验收测试。"
  >
    <ElSelect v-if="data.persons.length" v-model="personFilter" style="width: 180px">
      <ElOption value="" label="全部审批人" />
      <ElOption
        v-for="person in data.persons"
        :key="person.id"
        :value="person.id"
        :label="person.name"
      />
    </ElSelect>
    <ElSelect v-if="data.persons.length" v-model="statusFilter" style="width: 140px">
      <ElOption value="PENDING" label="只看待办" />
      <ElOption value="ALL" label="全部状态" />
    </ElSelect>
  </PageHead>

  <ErrorPanel v-if="error" :error="error" />

  <PanelCard v-else-if="!loading && !data.persons.length">
    <EmptyState title="还没有人员" hint="审批任务分配给具体人员，先维护人员再配置审批流。">
      <a class="btn btn--sm" href="#/people">去维护人员</a>
    </EmptyState>
  </PanelCard>

  <PanelCard v-else>
    <div v-if="showWaitingNote" class="note note--work waiting-note">
      当前有 {{ waiting.length }} 条待办等待处理。
    </div>

    <DataTable
      :columns="columns"
      :rows="data.tasks"
      :loading="loading"
      :empty-title="emptyTitle"
      :empty-hint="emptyHint"
    >
      <template #cell-instance_title="{ row }">
        <a class="cell-title" :href="`#/instances/${row.instance_id}`">
          {{ row.instance_title || '（无标题）' }}
        </a>
      </template>
      <template #cell-business_key="{ row }">
        <span class="code">{{ row.business_key || '—' }}</span>
      </template>
      <template #cell-node_name="{ row }">{{ row.node_name || '—' }}</template>
      <template #cell-approver_person_id="{ row }">
        {{ personNameOf(row.approver_person_id) }}
      </template>
      <template #cell-status="{ row }">
        <StatusTag :status="row.status" />
      </template>
      <template #cell-created_at="{ row }">
        <span class="muted">{{ formatTime(row.created_at) }}</span>
      </template>
      <template #cell-duration_ms="{ row }">
        <span class="muted">{{ formatDuration(row.duration_ms) }}</span>
      </template>
      <template #cell-actions="{ row }">
        <template v-if="row.status === 'PENDING'">
          <button class="btn--link btn--sm" type="button" @click="openDecision(row, 'approve')">
            同意
          </button>
          <button
            class="btn--link btn--sm is-danger"
            type="button"
            @click="openDecision(row, 'reject')"
          >
            拒绝
          </button>
        </template>
        <a class="btn--link btn--sm" :href="`#/instances/${row.instance_id}`">详情</a>
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
/* 旧版的 .muted / .cell-title 只写在 .tbl 作用域里，AntD 的表格里匹配不到，这里补一条 */
.muted {
  color: var(--ink-3);
}
.cell-title {
  font-weight: 600;
}
/* 待办提示条与表格之间留一段间距（旧版靠面板头部的 padding 分隔） */
.waiting-note {
  margin-bottom: 14px;
}
</style>
