<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'

import { actionApi } from '@/api/modules/action'
import type { ExecutionRecord } from '@/api/types'
import JsonBlock from '@/components/common/JsonBlock.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import Breadcrumb from '@/components/layout/Breadcrumb.vue'
import ErrorPanel from '@/components/layout/ErrorPanel.vue'
import KvDescriptions from '@/components/layout/KvDescriptions.vue'
import PageHead from '@/components/layout/PageHead.vue'
import PanelCard from '@/components/layout/PanelCard.vue'
import { useAsyncPage } from '@/composables/useAsyncPage'
import { formatDuration, formatTime, shortId } from '@/utils/format'

const route = useRoute()
const recordId = computed(() => String(route.params.id || ''))

const {
  data: record,
  error,
  refresh,
} = useAsyncPage(() => actionApi.executionRecord(recordId.value), null as ExecutionRecord | null)

// 同组件复用（从一条记录跳到另一条）时参数变了必须重取：旧版靠 hash 变化整体重渲染
watch(recordId, () => void refresh())

onMounted(refresh)

const pairs = computed(() => {
  const item = record.value
  if (!item) return []
  return [
    { key: '请求地址', slot: 'requestUrl' },
    { key: '调用方式', slot: 'httpMethod' },
    { key: 'HTTP 状态码', slot: 'httpStatus' },
    { key: '耗时', value: formatDuration(item.duration_ms) },
    { key: '开始时间', value: formatTime(item.started_at) },
    { key: '结束时间', value: formatTime(item.finished_at) },
    { key: '超时设置', value: item.timeout_ms ? `${item.timeout_ms} ms` : '—' },
    { key: '成功状态码', slot: 'successCodes' },
    { key: '失败原因', slot: 'errorMessage' },
  ]
})

/** 成功状态码为空表示全部 2xx（后端默认口径） */
const successCodesText = computed(() => {
  const codes = record.value?.success_status_codes
  return codes && codes.length ? codes.join(', ') : '全部 2xx'
})

/**
 * 响应正文是后端按固定上限截断保存的**原文**：能解析成 JSON 就用 JsonBlock 美化，
 * 解析不了（被截断的 JSON、纯文本响应）原样显示 —— 否则 JsonBlock 会把整段文本
 * 当成一个字符串再序列化，满屏转义符反而看不清。
 */
const responseJson = computed<unknown>(() => {
  const body = record.value?.response_body
  if (!body) return null
  try {
    return JSON.parse(body)
  } catch {
    return body
  }
})
</script>

<template>
  <template v-if="record">
    <Breadcrumb
      :items="[{ text: '执行记录', hash: '#/executions' }, { text: shortId(record.id) }]"
    />

    <PageHead :title="`执行记录 · ${record.action_code}`">
      <template #note>
        审批实例 <span class="code">{{ record.approval_instance_id }}</span>
      </template>
      <a class="btn" :href="`#/instances/${record.approval_instance_id}`">查看审批详情</a>
    </PageHead>

    <PanelCard title="调用结果">
      <template #actions>
        <StatusTag :status="record.status" />
      </template>
      <KvDescriptions :pairs="pairs">
        <template #requestUrl>
          <span class="code">{{ record.request_url || '—' }}</span>
        </template>
        <template #httpMethod>
          <span class="code">{{ record.http_method || '—' }}</span>
        </template>
        <template #httpStatus>
          <span class="code">{{ record.http_status_code ?? '—' }}</span>
        </template>
        <template #successCodes>
          <span class="code">{{ successCodesText }}</span>
        </template>
        <template #errorMessage>
          <span v-if="record.error_message" class="is-error">{{ record.error_message }}</span>
          <span v-else>—</span>
        </template>
      </KvDescriptions>
    </PanelCard>

    <PanelCard title="请求参数">
      <template #actions>
        <span class="panel__note">审批实例固化下来的执行参数，认证信息不出现在记录里</span>
      </template>
      <JsonBlock :value="record.request_payload || {}" />
    </PanelCard>

    <PanelCard title="响应正文">
      <template #actions>
        <span class="panel__note">保存时已按固定上限截断</span>
      </template>
      <JsonBlock :value="responseJson" empty="（无响应正文）" />
    </PanelCard>
  </template>

  <ErrorPanel v-else-if="error" :error="error" />

  <div v-else class="loading">正在读取数据…</div>
</template>

<style scoped>
.is-error {
  color: var(--cinnabar);
}
</style>
