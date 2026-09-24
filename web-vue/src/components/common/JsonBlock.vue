<script setup lang="ts">
import { stringifyJson } from '@/utils/json'

// 只读 JSON 块，对应旧版 .raw-json。
const props = defineProps<{
  value: unknown
  empty?: string
}>()
</script>

<template>
  <pre class="raw-json">{{
    props.value === null || props.value === undefined
      ? props.empty || '—'
      : stringifyJson(props.value)
  }}</pre>
</template>
