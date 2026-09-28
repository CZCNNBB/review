<script setup lang="ts">
import { computed } from 'vue'

import JsonBlock from '@/components/common/JsonBlock.vue'
import KvDescriptions from '@/components/layout/KvDescriptions.vue'
import type { JSONSchema } from '@/types/domain'
import { formFieldLabels } from '@/utils/schemaForm'

const props = defineProps<{
  form: Record<string, unknown>
  schema?: JSONSchema | null
}>()

/** 按审批单绑定版本的表单 Schema 显示中文字段名，并保留原字段名供排查。 */
const pairs = computed(() => {
  const labels = formFieldLabels(props.schema)
  return Object.entries(props.form).map(([key, raw], index) => ({
    key: labels[`approval_form.${key}`] || key,
    hint: `字段名 ${key}`,
    slot: `form-value-${index}`,
    json: raw !== null && typeof raw === 'object',
    text: raw === null || raw === undefined ? '—' : String(raw),
    raw,
  }))
})
</script>

<template>
  <KvDescriptions v-if="pairs.length" :pairs="pairs">
    <template v-for="pair in pairs" :key="pair.slot" #[pair.slot]>
      <JsonBlock v-if="pair.json" :value="pair.raw" />
      <span v-else class="code">{{ pair.text }}</span>
    </template>
  </KvDescriptions>
  <div v-else class="note">这张审批单没有填写表单内容。</div>
</template>
