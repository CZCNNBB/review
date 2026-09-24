<script setup lang="ts">
// 页头：标题 + 说明 + 右侧操作区。对应原版的 pageHead(title, note, actionsHtml)。
// 说明文案允许富文本，用 note 插槽；纯文本直接传 note 属性即可。
defineProps<{
  title: string
  note?: string
}>()
</script>

<template>
  <div class="page-head">
    <div>
      <h2 class="page-head__title">{{ title }}</h2>
      <div v-if="note || $slots.note" class="page-head__note">
        <slot name="note">{{ note }}</slot>
      </div>
    </div>
    <div class="page-head__actions">
      <slot />
    </div>
  </div>
</template>
