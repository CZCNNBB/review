<script setup lang="ts">
import { computed } from 'vue'

import { stampTone, statusText } from '@/utils/status'

// 审批单的状态戳：签名元素，绝不被组件库同化。
// 1.5px 描边、.14em 字距、-2° 旋转，来自旧版 .stamp。
const props = defineProps<{
  status?: string | null
  large?: boolean
}>()

const tone = computed(() => stampTone(props.status))
</script>

<template>
  <span class="stamp" :class="[`stamp--${tone}`, { 'stamp--lg': large !== false }]">
    {{ statusText(status) }}
  </span>
</template>
