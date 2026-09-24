<script lang="ts">
/**
 * 时间线上的一条审批意见。字段取组件真正用到的那几个：
 * 共享类型（api/types.ts）里记录写的是 approver_person_id / approver_name / result，
 * 后端实际返回的是 operator_person_id / operator_snapshot / action —— 两套都收，
 * 由页面在入口处归一，组件本身不做接口形状的判断。
 */
export interface TimelineRecord {
  approver_person_id?: string | null
  approver_name?: string | null
  result?: string | null
  comment?: string | null
  created_at?: string | null
}

/** 时间线上的一个节点执行。沿用旧版 app.js 的字段口径。 */
export interface TimelineExecution {
  id?: string
  node_name: string
  status: string
  /** 后端字段：进入该节点的时间 */
  entered_at?: string | null
  /** 共享类型里的同义字段，后端在另一套表结构下才给 */
  started_at?: string | null
  duration_ms?: number | null
  next_node_name?: string | null
  /** 走出这个节点时命中条件分支还是走默认路径 */
  condition_hit?: boolean | null
  approval_records?: TimelineRecord[]
}
</script>

<script setup lang="ts">
import { computed } from 'vue'

import StatusTag from '@/components/common/StatusTag.vue'
import EmptyState from '@/components/layout/EmptyState.vue'
import { formatDuration, formatTime, shortId } from '@/utils/format'
import { statusText } from '@/utils/status'

// 会签时间线：签名元素，整块自研 —— 旧版是 app.js 里拼出来的内联 HTML，
// 视觉由 styles/signature.css 的 .timeline / .timeline__dot / .opinion 锁定，
// 两个组件库都没有对应物，不接它们的 Steps 或 Timeline。
const props = defineProps<{
  /** 实例实际经过的节点，按执行顺序 */
  executions: TimelineExecution[]
  /** 人员 id → 姓名。缺这条映射时退回短 ID（旧版 personNameOf 的兜底） */
  persons?: Record<string, string>
}>()

/** 节点状态 → .timeline__item--done / --reject / --active，其余状态沿用默认灰点 */
const TONE: Record<string, string> = {
  COMPLETED: 'done',
  REJECTED: 'reject',
  ACTIVE: 'active',
}

/** 意见动作 → 中文。只认后端约定的 APPROVE / REJECT，别的状态走状态文案。 */
function actionText(action?: string | null): string {
  if (action === 'APPROVE') return '同意'
  if (action === 'REJECT') return '拒绝'
  return statusText(action)
}

/** 操作人：快照里的姓名优先，其次查人员表，最后退回短 ID（旧版同此顺序）。 */
function nameOf(record: TimelineRecord): string {
  const personId = record.approver_person_id
  const fromList = personId ? props.persons?.[personId] : ''
  return record.approver_name || fromList || shortId(personId)
}

// 模板里不写判断：进入时间、耗时的兜底、去向文案都在这里拼好。
const items = computed(() =>
  props.executions.map((execution, index) => ({
    key: execution.id || `${execution.node_name}-${index}`,
    tone: TONE[execution.status] || '',
    name: execution.node_name,
    status: execution.status,
    enteredAt: formatTime(execution.entered_at || execution.started_at),
    duration: formatDuration(execution.duration_ms),
    next: execution.next_node_name
      ? {
          name: execution.next_node_name,
          condition:
            execution.condition_hit === true
              ? '（条件命中）'
              : execution.condition_hit === false
                ? '（默认路径）'
                : '',
        }
      : null,
    opinions: (execution.approval_records || []).map((record) => ({
      who: nameOf(record),
      action: actionText(record.result),
      at: formatTime(record.created_at),
      comment: record.comment || '',
    })),
  })),
)
</script>

<template>
  <EmptyState v-if="!executions.length" title="流程还没有产生节点执行记录" />

  <div v-else class="timeline">
    <div
      v-for="item in items"
      :key="item.key"
      class="timeline__item"
      :class="item.tone ? `timeline__item--${item.tone}` : ''"
    >
      <div class="timeline__dot"></div>
      <div class="timeline__head">
        <span class="timeline__name">{{ item.name }}</span>
        <StatusTag :status="item.status" />
        <span class="timeline__meta">{{ item.enteredAt }} · 耗时 {{ item.duration }}</span>
        <span v-if="item.next" class="timeline__meta">
          → {{ item.next.name }}{{ item.next.condition }}
        </span>
      </div>

      <div v-for="(opinion, index) in item.opinions" :key="index" class="opinion">
        <span class="opinion__who">{{ opinion.who }}</span>
        {{ opinion.action }} · {{ opinion.at }}
        <div v-if="opinion.comment" class="opinion__comment">{{ opinion.comment }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 意见正文另起一行。旧版是内联 style，收进类里 */
.opinion__comment {
  margin-top: 4px;
}
</style>
