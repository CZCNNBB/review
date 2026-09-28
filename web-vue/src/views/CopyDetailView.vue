<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'

import { safe } from '@/api/http'
import { actionApi } from '@/api/modules/action'
import { approvalApi } from '@/api/modules/approval'
import { orgApi } from '@/api/modules/org'
import { processApi } from '@/api/modules/process'
import type { ApprovalInstanceDetail, BusinessAction, Person } from '@/api/types'
import ApprovalFormDetails from '@/components/common/ApprovalFormDetails.vue'
import ApprovalTimeline from '@/components/common/ApprovalTimeline.vue'
import type { TimelineExecution } from '@/components/common/ApprovalTimeline.vue'
import CopyButton from '@/components/common/CopyButton.vue'
import StatusStamp from '@/components/common/StatusStamp.vue'
import Breadcrumb from '@/components/layout/Breadcrumb.vue'
import ErrorPanel from '@/components/layout/ErrorPanel.vue'
import KvDescriptions from '@/components/layout/KvDescriptions.vue'
import PageHead from '@/components/layout/PageHead.vue'
import PanelCard from '@/components/layout/PanelCard.vue'
import { useAsyncPage } from '@/composables/useAsyncPage'
import type { JSONSchema } from '@/types/domain'
import { formatDuration, formatTime, shortId } from '@/utils/format'

interface CopyDetailPage {
  detail: ApprovalInstanceDetail | null
  formSchema: JSONSchema | null
  persons: Person[]
  actions: BusinessAction[]
}

const EMPTY_PAGE: CopyDetailPage = {
  detail: null,
  formSchema: null,
  persons: [],
  actions: [],
}

const route = useRoute()
const copyId = computed(() => String(route.params.id || ''))
const personId = computed(() => String(route.query.person || ''))

const { data: page, loading, error, refresh } = useAsyncPage<CopyDetailPage>(
  async () => {
    if (!personId.value) throw new Error('缺少抄送收件人，请从抄送列表打开审批单')

    // 详情接口先校验这条抄送确实属于所选人员；辅助数据失败时仍显示审批单本身。
    const detail = await approvalApi.copiedInstance(copyId.value, personId.value)
    const [graph, persons, actions] = await Promise.all([
      safe(processApi.graph(detail.process_version_id), null),
      safe(orgApi.persons(200), [] as Person[]),
      safe(actionApi.list(200), [] as BusinessAction[]),
    ])
    return { detail, formSchema: graph?.form_schema || null, persons, actions }
  },
  EMPTY_PAGE,
)

const detail = computed(() => page.value.detail)
const personNames = computed<Record<string, string>>(() =>
  Object.fromEntries(page.value.persons.map((person) => [person.id, person.name])),
)

/** 将后端审批记录按节点归组，交给审批详情共用的时间线组件渲染。 */
const timeline = computed<TimelineExecution[]>(() => {
  if (!detail.value) return []
  const recordsByExecution = new Map<string, NonNullable<TimelineExecution['approval_records']>>()
  for (const record of detail.value.records) {
    const records = recordsByExecution.get(record.node_execution_id) || []
    records.push({
      approver_person_id: record.operator_person_id,
      approver_name: String(record.operator_snapshot?.name || ''),
      result: record.action,
      comment: record.comment,
      created_at: record.created_at,
    })
    recordsByExecution.set(record.node_execution_id, records)
  }
  return detail.value.node_executions.map((execution) => ({
    ...execution,
    approval_records: recordsByExecution.get(execution.id) || [],
  }))
})

/** 人员快照优先，目录姓名其次，最后用短 ID 标识发起人。 */
const applicantName = computed(() => {
  const current = detail.value
  if (!current) return '—'
  const snapshotName = current.applicant_snapshot?.name
  if (snapshotName) return String(snapshotName)
  return personNames.value[current.applicant_person_id || ''] || shortId(current.applicant_person_id)
})

/** 业务动作显示中文名称；旧动作已删除时保留动作编码。 */
const actionName = computed(() => {
  const code = detail.value?.action_code
  if (!code) return ''
  return page.value.actions.find((action) => action.action_code === code)?.name || code
})

/** 后端未返回耗时时，根据审批单的起止时间计算展示值。 */
const elapsedMs = computed(() => {
  const current = detail.value
  if (!current) return null
  if (current.duration_ms !== null) return current.duration_ms
  const started = new Date(current.started_at).getTime()
  const ended = current.finished_at ? new Date(current.finished_at).getTime() : Date.now()
  return ended - started
})

const detailPairs = computed(() => [
  { key: '审批实例', slot: 'instanceId' },
  { key: '发起人', value: applicantName.value },
  { key: '发起时间', value: formatTime(detail.value?.started_at) },
  { key: '结束时间', value: formatTime(detail.value?.finished_at) },
  { key: '业务动作', slot: 'actionCode' },
])

watch([copyId, personId], () => void refresh())
onMounted(refresh)
</script>

<template>
  <Breadcrumb
    :items="[{ text: '工作台', hash: `#/workbench?type=COPY&person=${personId}` }, { text: detail?.title || '审批单' }]"
  />
  <ErrorPanel v-if="error" :error="error" />

  <template v-else-if="detail">
    <PageHead
      :title="detail.title"
      :note="`业务单号 ${detail.business_key} · ${detail.process_name} V${detail.process_version_no}`"
    >
      <StatusStamp :status="detail.status" />
    </PageHead>

    <PanelCard title="审批单">
      <template #actions>
        <span class="panel__note">
          {{ detail.current_node ? `当前停在「${detail.current_node.node_name}」` : '流程已结束' }}
          · 已用时 {{ formatDuration(elapsedMs) }}
        </span>
      </template>
      <KvDescriptions :pairs="detailPairs">
        <template #instanceId>
          <span class="code">{{ detail.id }}</span>
          <CopyButton :text="detail.id" />
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

    <PanelCard title="审批表单">
      <ApprovalFormDetails :form="detail.approval_form" :schema="page.formSchema" />
    </PanelCard>

    <PanelCard title="会签时间线">
      <ApprovalTimeline :executions="timeline" :persons="personNames" />
    </PanelCard>
  </template>

  <div v-else-if="loading" class="loading">正在读取数据…</div>
  <PanelCard v-else>审批单不存在</PanelCard>
</template>

<style scoped>
/* 动作编码和次要说明与审批详情页保持一致。 */
.action-code {
  margin-left: 8px;
  color: var(--ink-3);
}
.muted {
  color: var(--ink-3);
}
</style>
