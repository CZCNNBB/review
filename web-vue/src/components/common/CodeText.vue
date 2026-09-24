<script setup lang="ts">
// 行内代码：ID、动作标识这类等宽内容。
defineProps<{
  text: string
}>()
</script>

<template>
  <span class="code">{{ text }}</span>
</template>
