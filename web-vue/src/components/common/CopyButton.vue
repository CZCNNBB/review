<script setup lang="ts">
import { copyText } from '@/composables/useClipboard'

// 复制按钮：对应旧版 copyButton()。
const props = defineProps<{
  text: string
  label?: string
  message?: string
}>()
</script>

<template>
  <button class="btn btn--link btn--sm" type="button" @click="copyText(props.text, props.message)">
    {{ props.label || '复制' }}
  </button>
</template>
