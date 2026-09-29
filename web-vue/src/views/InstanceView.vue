<script setup lang="ts">
import { ElButton, ElInput } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { safe } from '@/api/http'
import { actionApi } from '@/api/modules/action'
import { approvalApi } from '@/api/modules/approval'
import { orgApi } from '@/api/modules/org'
import { processApi } from '@/api/modules/process'
import type {
  ApprovalInstanceDetail,
  ApprovalRecord,
  ApprovalTask,
  ApprovalTimelineEntry,
  BusinessAction,
  ExecutionRecord,
  Person,
  Tenant,
} from '@/api/types'
import ApprovalDetailHero from '@/components/common/ApprovalDetailHero.vue'
import ApprovalDetailSections from '@/components/common/ApprovalDetailSections.vue'
import ApprovalTimeline from '@/components/common/ApprovalTimeline.vue'
import type { TimelineExecution, TimelineRecord } from '@/components/common/ApprovalTimeline.vue'
import ApprovalFormDetails from '@/components/common/ApprovalFormDetails.vue'
import CopyButton from '@/components/common/CopyButton.vue'
import DataTable from '@/components/common/DataTable.vue'
import type { ColumnSpec } from '@/components/common/DataTable.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import TaskDecisionDialog from '@/components/dialogs/TaskDecisionDialog.vue'
import Breadcrumb from '@/components/layout/Breadcrumb.vue'
import ErrorPanel from '@/components/layout/ErrorPanel.vue'
import KvDescriptions from '@/components/layout/KvDescriptions.vue'
import PageHead from '@/components/layout/PageHead.vue'
import PanelCard from '@/components/layout/PanelCard.vue'
import { useAsyncPage } from '@/composables/useAsyncPage'
import { useConfigStore } from '@/stores/config'
import { useCredentialsStore } from '@/stores/credentials'
import { formatDuration, formatTime, shortId } from '@/utils/format'
import { toastError, toastOk } from '@/utils/notify'
import type { JSONSchema } from '@/types/domain'

/** 页面用的审批详情，只保留展示所需的字段。 */
interface InstanceDetail {
  id: string
  title: string
  business_key: string
  process_name: string
  process_version_no: number | null
  status: string
  applicant_person_id: string | null
  applicant_name: string
  action_code: string | null
  started_at: string
  finished_at: string | null
  duration_ms: number | null
  current_node_name: string | null
  approval_form: Record<string, unknown>
  pending_tasks: ApprovalTask[]
}

/** 把后端审批记录转换为时间线组件的展示字段。 */
function normalizeRecord(record: ApprovalRecord): TimelineRecord {
  return {
    approver_person_id: record.operator_person_id,
    approver_name: String(record.operator_snapshot?.name || ''),
    result: record.action,
    comment: record.comment,
    created_at: record.created_at,
  }
}

/** 使用详情接口中已按节点归组的时间线，避免页面再次关联任务与意见。 */
function normalizeExecutions(entries: ApprovalTimelineEntry[]): TimelineExecution[] {
  return entries.map((entry) => ({
    ...entry.node_execution,
    approval_records: entry.records.map(normalizeRecord),
  }))
}

/** 将统一详情响应投影为页面所需的概要字段。 */
function normalizeInstance(source: ApprovalInstanceDetail): InstanceDetail {
  return {
    id: source.id,
    title: source.title,
    business_key: source.business_key,
    process_name: source.process_name,
    process_version_no: source.process_version_no,
    status: source.status,
    applicant_person_id: source.applicant_person_id,
    applicant_name: String(source.applicant_snapshot?.name || ''),
    action_code: source.action_code,
    started_at: source.started_at,
    finished_at: source.finished_at,
    duration_ms: source.duration_ms,
    current_node_name: source.current_node?.node_name || null,
    approval_form: source.approval_form,
    pending_tasks: source.pending_tasks,
  }
}

const pendingColumns: ColumnSpec[] = [
  { key: 'approver_person_id', title: '审批人', width: 150 },
  { key: 'node_name', title: '节点' },
  { key: 'created_at', title: '产生时间', width: 160 },
  { key: 'duration_ms', title: '已等待', width: 120, align: 'right' },
  { key: 'actions', title: '操作', width: 150, align: 'right' },
]

const route = useRoute()
const instanceId = computed(() => String(route.params.id || ''))

const config = useConfigStore()
const credentials = useCredentialsStore()

interface InstancePage {
  tenant: Tenant | null
  detail: InstanceDetail | null
  executions: TimelineExecution[]
  execution: ExecutionRecord | null
  persons: Person[]
  /** 这张单子所用版本的审批表单 Schema：字段的显示名只有这里有 */
  formSchema: JSONSchema | null
  /** 业务动作列表：把 action_code 翻成中文名 */
  actions: BusinessAction[]
}

const EMPTY_PAGE: InstancePage = {
  tenant: null,
  detail: null,
  executions: [],
  execution: null,
  persons: [],
  formSchema: null,
  actions: [],
}

const manualKey = ref('')

const {
  data: page,
  loading,
  error,
  refresh,
} = useAsyncPage<InstancePage>(async () => {
  // 详情接口按租户鉴权，管理台按使用记录自动借用发起审批的租户密钥（契约⑧）
  const borrowed = await credentials.forInstance(instanceId.value)
  // 借不到就退回配置里手动填的那把（旧版：credentials.key || config.apiKey）
  const apiKey = borrowed.key || config.apiKey
  if (!apiKey) {
    // 一把密钥都没有时不发请求，页面改显示「手动填密钥」面板
    return { ...EMPTY_PAGE, tenant: borrowed.tenant }
  }

  const [rawDetail, executions, persons] = await Promise.all([
    approvalApi.instance(instanceId.value, apiKey),
    safe(actionApi.executionRecords({ instanceId: instanceId.value }), [] as ExecutionRecord[]),
    // 人员名单只用来把人员 id 显示成姓名：单独失败不该把整页变成错误面板
    safe(orgApi.persons(200), [] as Person[]),
  ])

  // 给审批人看的东西不能是 JSON 键名：表单要按版本冻结的 Schema 显示中文名，
  // 所以拿到详情后再按它用的版本取一次图（Schema 在版本里，改了新版不影响这张老单子）。
  // 动作列表同理，把 action_code 翻成中文名。两者都是辅助信息，取不到就退化成键名/编码。
  const [graph, actions] = await Promise.all([
    safe(processApi.graph(rawDetail.process_version_id), null),
    safe(actionApi.list(200), [] as BusinessAction[]),
  ])

  return {
    tenant: borrowed.tenant,
    detail: normalizeInstance(rawDetail),
    executions: normalizeExecutions(rawDetail.timeline_entries),
    execution: executions[0] || null,
    persons,
    formSchema: graph?.form_schema || null,
    actions,
  }
}, EMPTY_PAGE)

const detail = computed(() => page.value.detail)
const tenant = computed(() => page.value.tenant)
const execution = computed(() => page.value.execution)

const personNames = computed<Record<string, string>>(() =>
  Object.fromEntries(page.value.persons.map((person) => [person.id, person.name])),
)

/** 人员目录有姓名时优先展示姓名，否则退回短 ID。 */
function personNameOf(personId?: string | null): string {
  const person = page.value.persons.find((item) => item.id === personId)
  return person ? person.name : shortId(personId)
}

/** 面板头部的「已用时」：接口没给 duration_ms 时用开始/结束时间兜底。 */
const elapsedMs = computed(() => {
  const current = detail.value
  if (!current) return null
  if (current.duration_ms !== null) return current.duration_ms
  if (!current.started_at) return null
  const started = new Date(current.started_at).getTime()
  const ended = current.finished_at ? new Date(current.finished_at).getTime() : Date.now()
  return ended - started
})

const detailPairs = computed(() => [
  { key: '审批实例', slot: 'instanceId' },
  { key: '所属租户', slot: 'tenant' },
  { key: '结束时间', value: formatTime(detail.value?.finished_at) },
  { key: '业务动作', slot: 'actionCode' },
])

/** action_code → 业务动作名。查不到就退回编码（动作被删或列表没取到）。 */
const actionNames = computed(
  () => new Map(page.value.actions.map((action) => [action.action_code, action.name])),
)

const actionName = computed(() => {
  const code = detail.value?.action_code
  if (!code) return ''
  return actionNames.value.get(code) || code
})

const executionPairs = computed(() => {
  if (!execution.value) return []
  return [
    { key: '执行状态', slot: 'execStatus' },
    { key: '调用方式', slot: 'execCall' },
    { key: 'HTTP 状态码', slot: 'execHttpStatus' },
    { key: '耗时', value: formatDuration(execution.value.duration_ms) },
    { key: '失败原因', slot: 'execError' },
  ]
})

/** 手动填的密钥写进浏览器配置：之后租户侧的接口都用它（旧版同此）。 */
async function useManualKey(): Promise<void> {
  const value = manualKey.value.trim()
  if (!value) {
    toastError('请先填入密钥')
    return
  }
  config.setApiKey(value)
  await refresh()
}

/** 处理任务成功后刷新审批单，让状态和待办即时更新。 */
async function afterDecided(): Promise<void> {
  toastOk('处理完成')
  await refresh()
}

/* ---------------------------------------------------------------------------
   处理待办：同意 / 拒绝复用同一个弹窗
   --------------------------------------------------------------------------- */

const decisionOpen = ref(false)
const decisionKind = ref<'approve' | 'reject'>('approve')
const decisionTask = ref<ApprovalTask | null>(null)

const decisionApproverName = computed(() => personNameOf(decisionTask.value?.approver_person_id))

/** 为选中的审批任务打开同意或拒绝弹窗。 */
function openDecision(task: ApprovalTask, kind: 'approve' | 'reject'): void {
  decisionKind.value = kind
  decisionTask.value = task
  decisionOpen.value = true
}

// 同组件复用（从一张审批单跳到另一张）时参数变了必须重取：旧版靠 hash 变化整体重渲染
watch(instanceId, () => void refresh())

onMounted(refresh)
</script>

<template>
  <Breadcrumb
    :items="[
      { text: '工作台', hash: '#/workbench?type=APPROVAL' },
      { text: detail?.title || shortId(instanceId) },
    ]"
  />

  <ErrorPanel v-if="error" :error="error" />

  <template v-else-if="detail">
    <ApprovalDetailHero
      kind="APPROVAL"
      :title="detail.title"
      :status="detail.status"
      :business-key="detail.business_key"
      :process-label="`${detail.process_name} V${detail.process_version_no ?? '—'}`"
      :current-node-name="detail.current_node_name"
      :applicant-name="detail.applicant_name || personNameOf(detail.applicant_person_id)"
      :started-at="formatTime(detail.started_at)"
      :duration="formatDuration(elapsedMs)"
      :pending-count="detail.pending_tasks.length"
    />

    <section
      v-if="detail.pending_tasks.length"
      class="decision-panel"
      aria-labelledby="pending-heading"
    >
      <div class="decision-panel__heading">
        <div>
          <span class="decision-panel__eyebrow">需要处理</span>
          <h2 id="pending-heading">{{ detail.pending_tasks.length }} 条审批待办</h2>
        </div>
        <p>管理台代为处理时使用任务所属审批人的身份，仅用于联调和验收。</p>
      </div>

      <DataTable
        :columns="pendingColumns"
        :rows="detail.pending_tasks"
        :loading="loading"
        empty-title="没有待办"
      >
        <template #cell-approver_person_id="{ row }">
          <span class="cell-title">{{ personNameOf(row.approver_person_id) }}</span>
        </template>
        <template #cell-node_name="{ row }">{{ row.node_name || '—' }}</template>
        <template #cell-created_at="{ row }">
          <span class="muted">{{ formatTime(row.created_at) }}</span>
        </template>
        <template #cell-duration_ms="{ row }">
          <span class="muted">{{ formatDuration(row.duration_ms) }}</span>
        </template>
        <template #cell-actions="{ row }">
          <button
            class="btn btn--primary btn--sm"
            type="button"
            @click="openDecision(row, 'approve')"
          >
            同意
          </button>
          <button
            class="btn btn--danger btn--sm decision-panel__reject"
            type="button"
            @click="openDecision(row, 'reject')"
          >
            拒绝
          </button>
        </template>
      </DataTable>
    </section>

    <ApprovalDetailSections>
      <template #form>
        <ApprovalFormDetails :form="detail.approval_form" :schema="page.formSchema" />
      </template>

      <template #timeline>
        <ApprovalTimeline :executions="page.executions" :persons="personNames" />
      </template>

      <template v-if="detail.action_code" #extra>
        <PanelCard title="业务执行">
          <template #actions>
            <a v-if="execution" class="btn btn--sm" :href="`#/executions/${execution.id}`">
              查看完整记录
            </a>
          </template>

          <KvDescriptions v-if="execution" :pairs="executionPairs">
            <template #execStatus>
              <StatusTag :status="execution.status" />
            </template>
            <template #execCall>
              <span>{{ actionName }}</span>
              <span class="code action-code"
                >{{ execution.http_method }} {{ execution.relative_path }}</span
              >
            </template>
            <template #execHttpStatus>
              <span class="code">{{ execution.http_status_code ?? '—' }}</span>
            </template>
            <template #execError>
              <span v-if="execution.error_message" class="exec-error">{{
                execution.error_message
              }}</span>
              <span v-else>—</span>
            </template>
          </KvDescriptions>

          <div v-else class="note">审批还未通过，或通过后尚未创建执行记录。</div>
        </PanelCard>
      </template>

      <template #metadata>
        <KvDescriptions :pairs="detailPairs">
          <template #instanceId>
            <span class="code">{{ detail.id }}</span>
            <CopyButton :text="detail.id" />
          </template>
          <template #tenant>
            <span v-if="tenant">{{ tenant.name }}（{{ tenant.code }}）</span>
            <span v-else class="muted">全局模式，无租户归属</span>
          </template>
          <template #actionCode>
            <template v-if="detail.action_code">
              <span>{{ actionName }}</span>
              <span class="code action-code">{{ detail.action_code }}</span>
            </template>
            <span v-else class="muted">不触发业务执行</span>
          </template>
        </KvDescriptions>
      </template>
    </ApprovalDetailSections>
  </template>

  <div v-else-if="loading" class="loading">正在读取数据…</div>

  <template v-else>
    <PageHead
      title="审批详情"
      note="详情接口在租户模式下要求 X-API-Key，管理台会自动借用发起审批的租户密钥。"
    />

    <PanelCard title="手动填密钥">
      <div class="note note--wait">
        没有解析到可用的租户密钥：该审批实例可能没有使用记录（全局模式发起），或者对应租户的 API Key
        全部被撤销。可以在租户页面重新签发一个密钥。
      </div>
      <p class="manual-key__hint">也可以临时指定一个密钥查询本次请求：</p>
      <div class="manual-key">
        <ElInput v-model="manualKey" placeholder="X-API-Key" />
        <ElButton @click="useManualKey">使用该密钥</ElButton>
      </div>
    </PanelCard>
  </template>

  <TaskDecisionDialog
    v-model:open="decisionOpen"
    :kind="decisionKind"
    :task="decisionTask"
    :approver-name="decisionApproverName"
    @decided="afterDecided"
  />
</template>

<style scoped>
/* 待办操作紧随概览区出现，让需要处理的事项先于表单与历史记录被看到。 */
.decision-panel {
  margin-bottom: var(--sp-5);
  border: 1px solid var(--indigo-line);
  border-radius: var(--radius-lg);
  background: var(--surface);
  overflow: hidden;
}
.decision-panel__heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--sp-3);
  flex-wrap: wrap;
  padding: var(--sp-4);
  background: var(--indigo-wash);
}
.decision-panel__eyebrow {
  color: var(--indigo);
  font-size: var(--fs-xs);
  font-weight: 700;
}
.decision-panel__heading h2 {
  margin-top: var(--sp-1);
  font-size: var(--fs-lg);
}
.decision-panel__heading p {
  color: var(--ink-2);
  font-size: var(--fs-sm);
}
.decision-panel__reject {
  margin-left: var(--sp-2);
}
/* 旧版的 .muted / .cell-title 只写在 .tbl 作用域里，AntD 的表格里匹配不到，这里补一条 */
.muted {
  color: var(--ink-3);
}
.cell-title {
  font-weight: 600;
}
/* 失败原因用朱砂色点出来（旧版是内联 style） */
.exec-error {
  color: var(--cinnabar);
}
/* 中文名后面跟的编码/调用地址：留着给联调看，但不抢视线 */
.action-code {
  margin-left: 8px;
  color: var(--ink-3);
}
/* 手动填密钥：一段说明 + 一行输入 */
.manual-key__hint {
  margin: 14px 0 8px;
  font-size: 13px;
  color: var(--ink-2);
}
.manual-key {
  display: flex;
  gap: 8px;
  max-width: 520px;
}
</style>
