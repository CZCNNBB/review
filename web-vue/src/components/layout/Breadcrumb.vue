<script setup lang="ts">
// 面包屑。最后一项是当前页，不带链接。
defineProps<{
  items: Array<{ text: string; hash?: string }>
}>()
</script>

<template>
  <div class="breadcrumb">
    <span v-for="(item, index) in items" :key="item.text">
      <a v-if="item.hash && index < items.length - 1" :href="item.hash">{{ item.text }}</a>
      <template v-else>{{ item.text }}</template>
    </span>
  </div>
</template>
