<script setup lang="ts">
import { ElButton, ElInput } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { safe } from '@/api/http'
import { actionApi } from '@/api/modules/action'
import { approvalApi } from '@/api/modules/approval'
import { orgApi } from '@/api/modules/org'
import { processApi } from '@/api/modules/process'
import type { ApprovalTask, BusinessAction, ExecutionRecord, Person, Tenant } from '@/api/types'
import ApprovalTimeline from '@/components/common/ApprovalTimeline.vue'
import type { TimelineExecution, TimelineRecord } from '@/components/common/ApprovalTimeline.vue'
import CopyButton from '@/components/common/CopyButton.vue'
import DataTable from '@/components/common/DataTable.vue'
import type { ColumnSpec } from '@/components/common/DataTable.vue'
import JsonBlock from '@/components/common/JsonBlock.vue'
import StatusStamp from '@/components/common/StatusStamp.vue'
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
import { formFieldLabels } from '@/utils/schemaForm'
import type { JSONSchema } from '@/types/domain'

/** 待办里还有 duration_ms（「已等待」列要用），共享类型没写，本地补上。 */
type TaskRow = ApprovalTask & { duration_ms?: number | null }

/** 页面用的审批详情：只留展示需要的字段，接口的几种形状在下面归一成这一份。 */
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
  pending_tasks: TaskRow[]
}

/**
 * 详情接口的线上形状。
 *
 * 后端返回的是平铺字段（与旧版 web/app.js 一致），而 api/types.ts 声明的是
 * { instance, pending_tasks, … } 的嵌套形状 —— 两套都可能出现，所以这里按平铺读、
 * 嵌套兜底。契约与实现错位时，页面不该整页空白。
 */
interface InstanceWire {
  id?: string
  title?: string
  business_key?: string
  process_name?: string
  process_version_no?: number | null
  status?: string
  applicant_person_id?: string | null
  applicant_snapshot?: { name?: string | null } | null
  action_code?: string | null
  started_at?: string
  finished_at?: string | null
  duration_ms?: number | null
  current_node?: { node_name?: string | null } | null
  current_node_name?: string | null
  approval_form?: Record<string, unknown>
  pending_tasks?: TaskRow[]
  /** 嵌套形状：上面这些字段挂在这一层下面 */
  instance?: InstanceWire
}

/** 时间线响应里的审批记录。后端是 operator_* / action，共享类型是 approver_* / result。 */
interface TimelineRecordWire extends TimelineRecord {
  operator_person_id?: string | null
  operator_snapshot?: { name?: string | null } | null
  action?: string | null
}

function normalizeRecord(record: TimelineRecordWire): TimelineRecord {
  return {
    approver_person_id: record.operator_person_id || record.approver_person_id || null,
    approver_name: record.operator_snapshot?.name || record.approver_name || null,
    result: record.action || record.result || null,
    comment: record.comment || null,
    created_at: record.created_at || null,
  }
}

/**
 * 时间线响应也有两套：后端返回 { entries: [{ node_execution, records }] }（与旧版
 * app.js 一致），共享类型声明的是 { node_executions: [...] }，这里连裸数组一起认，
 * 归一成节点执行数组，并把该节点的审批意见挂到 approval_records 上。
 */
function normalizeExecutions(raw: unknown): TimelineExecution[] {
  if (Array.isArray(raw)) return raw as TimelineExecution[]

  const wire = (raw || {}) as {
    node_executions?: TimelineExecution[]
    entries?: Array<{ node_execution?: TimelineExecution; records?: TimelineRecordWire[] }>
  }

  if (Array.isArray(wire.entries)) {
    return wire.entries.flatMap((entry) =>
      entry.node_execution
        ? [
            {
              ...entry.node_execution,
              approval_records: (entry.records || []).map(normalizeRecord),
            },
          ]
        : [],
    )
  }
  return Array.isArray(wire.node_executions) ? wire.node_executions : []
}

function normalizeInstance(raw: unknown, fallbackId: string): InstanceDetail {
  const wire = (raw || {}) as InstanceWire
  // 字段冲突时平铺优先：后端返回的就是平铺字段
  const source: InstanceWire = { ...(wire.instance || {}), ...wire }
  return {
    id: source.id || fallbackId,
    title: source.title || '（无标题）',
    business_key: source.business_key || '—',
    process_name: source.process_name || '—',
    process_version_no: source.process_version_no ?? null,
    status: source.status || '',
    applicant_person_id: source.applicant_person_id ?? null,
    applicant_name: source.applicant_snapshot?.name || '',
    action_code: source.action_code ?? null,
    started_at: source.started_at || '',
    finished_at: source.finished_at ?? null,
    duration_ms: typeof source.duration_ms === 'number' ? source.duration_ms : null,
    current_node_name: source.current_node?.node_name || source.current_node_name || null,
    approval_form: source.approval_form || {},
    pending_tasks: source.pending_tasks || [],
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

  const [rawDetail, rawTimeline, executions, persons] = await Promise.all([
    approvalApi.instance(instanceId.value, apiKey),
    approvalApi.timeline(instanceId.value, apiKey),
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
    detail: normalizeInstance(rawDetail, instanceId.value),
    executions: normalizeExecutions(rawTimeline),
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
  {
    key: '发起人',
    value: detail.value?.applicant_name || personNameOf(detail.value?.applicant_person_id),
  },
  { key: '发起时间', value: formatTime(detail.value?.started_at) },
  { key: '结束时间', value: formatTime(detail.value?.finished_at) },
  { key: '业务动作', slot: 'actionCode' },
])

/** 审批表单字段的中文名：与流程编辑器共用同一份映射（都来自版本的 form_schema）。 */
const fieldLabels = computed(() => formFieldLabels(page.value.formSchema))

/** action_code → 业务动作名。查不到就退回编码（动作被删或列表没取到）。 */
const actionNames = computed(
  () => new Map(page.value.actions.map((action) => [action.action_code, action.name])),
)

const actionName = computed(() => {
  const code = detail.value?.action_code
  if (!code) return ''
  return actionNames.value.get(code) || code
})

// 表单是业务系统自己定的键值，每一项都要一个插槽：槽名按序号生成，
// 模板里用动态槽名逐个接上（对象值摆 JsonBlock，标量按文本显示）。
// 标签取 Schema 里的显示名 —— 给审批人看的是「金额」，不是「JinEr」；
// 原始字段名挂在标签的悬停提示里，联调时还找得到。
const formPairs = computed(() =>
  Object.entries(detail.value?.approval_form || {}).map(([key, raw], index) => {
    const label = fieldLabels.value[`approval_form.${key}`] || key
    return {
      key: label,
      hint: `字段名 ${key}`,
      slot: `form-value-${index}`,
      json: raw !== null && typeof raw === 'object',
      text: raw === null || raw === undefined ? '—' : String(raw),
      raw,
    }
  }),
)

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

async function afterDecided(): Promise<void> {
  toastOk('处理完成')
  await refresh()
}

/* ---------------------------------------------------------------------------
   处理待办：同意 / 拒绝复用同一个弹窗
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

// 同组件复用（从一张审批单跳到另一张）时参数变了必须重取：旧版靠 hash 变化整体重渲染
watch(instanceId, () => void refresh())

onMounted(refresh)
</script>

<template>
  <Breadcrumb
    :items="[{ text: '待办任务', hash: '#/tasks' }, { text: detail?.title || shortId(instanceId) }]"
  />

  <ErrorPanel v-if="error" :error="error" />

  <template v-else-if="detail">
    <PageHead
      :title="detail.title"
      :note="`业务单号 ${detail.business_key} · ${detail.process_name} V${detail.process_version_no ?? '—'}`"
    >
      <StatusStamp :status="detail.status" />
    </PageHead>

    <PanelCard title="审批单">
      <template #actions>
        <span class="panel__note">
          {{ detail.current_node_name ? `当前停在「${detail.current_node_name}」` : '流程已结束' }}
          · 已用时 {{ formatDuration(elapsedMs) }}
        </span>
      </template>

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
    </PanelCard>

    <PanelCard v-if="formPairs.length" title="审批表单">
      <KvDescriptions :pairs="formPairs">
        <template v-for="pair in formPairs" :key="pair.key" #[pair.slot]>
          <JsonBlock v-if="pair.json" :value="pair.raw" />
          <span v-else class="code">{{ pair.text }}</span>
        </template>
      </KvDescriptions>
    </PanelCard>

    <PanelCard v-if="detail.pending_tasks.length" title="等待处理的待办">
      <template #actions>
        <span class="panel__note">
          管理台代为处理时使用任务所属审批人的身份，仅用于联调和验收
        </span>
      </template>

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
      </DataTable>
    </PanelCard>

    <PanelCard title="会签时间线">
      <ApprovalTimeline :executions="page.executions" :persons="personNames" />
    </PanelCard>

    <PanelCard v-if="detail.action_code" title="业务执行">
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
          <span class="code action-code">{{ execution.http_method }} {{ execution.relative_path }}</span>
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
