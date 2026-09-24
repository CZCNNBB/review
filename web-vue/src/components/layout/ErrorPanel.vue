<script setup lang="ts">
import { Result as AResult } from 'ant-design-vue'

// 整页失败态：说清哪里失败就行，没有"用示例数据先看看"这种退路。
const props = defineProps<{
  error: Error
}>()
</script>

<template>
  <div class="panel">
    <AResult status="warning" :title="'读取失败'" :sub-title="props.error.message" />
  </div>
</template>
