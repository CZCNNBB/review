<script setup lang="ts">
import { Empty as AEmpty } from 'ant-design-vue'

// 整页或面板内的空状态：一句标题 + 一句怎么办 + 一个入口按钮。
defineProps<{
  title: string
  hint?: string
}>()
</script>

<template>
  <AEmpty class="empty-state">
    <template #description>
      <div class="empty__title">{{ title }}</div>
      <div v-if="hint" class="empty__hint">{{ hint }}</div>
    </template>
    <slot />
  </AEmpty>
</template>

<style scoped>
.empty-state :deep(.ant-empty-image) {
  display: none;
}
.empty__title {
  color: var(--ink-2);
  font-weight: 600;
  margin-bottom: 4px;
}
.empty__hint {
  color: var(--ink-3);
  font-size: 13px;
  margin-bottom: 8px;
}
</style>
