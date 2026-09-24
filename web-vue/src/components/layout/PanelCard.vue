<script setup lang="ts">
// 内容容器：对应旧版的 .panel / .panel__head / .panel__body。
// 自研而不用 a-card / el-card：这层 padding、描边与间距是整站一致的骨架，
// 组件库的卡片会带自己的阴影与圆角，套上去反而要写一堆覆盖。
defineProps<{
  title?: string
}>()
</script>

<template>
  <section class="panel">
    <div v-if="title || $slots.actions || $slots.header" class="panel__head">
      <h3 v-if="title" class="panel__title">{{ title }}</h3>
      <slot name="header" />
      <div>
        <slot name="actions" />
      </div>
    </div>
    <div class="panel__body">
      <slot />
    </div>
  </section>
</template>
