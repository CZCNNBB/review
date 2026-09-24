<script setup lang="ts">
import { computed } from 'vue'

import { statusText, tagTone } from '@/utils/status'

// 状态标签是自研的：on/off/wait/work 四套语义色是业务契约，
// 两个库的 tag 都不带这套映射，套上去要写两遍覆盖还得两边同步。
const props = defineProps<{
  status?: string | null
  text?: string
}>()

const tone = computed(() => tagTone(props.status))
const label = computed(() => props.text || statusText(props.status))
</script>

<template>
  <span class="tag" :class="`tag--${tone}`">{{ label }}</span>
</template>
