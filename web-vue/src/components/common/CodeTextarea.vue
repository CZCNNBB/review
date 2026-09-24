<script setup lang="ts">
// JSON 输入框：两库都没有代码编辑器，旧版也只是等宽字体 + 固定行高。
// 值用 v-model，父组件负责解析与报错。
const model = defineModel<string>({ default: '' })

defineProps<{
  rows?: number
  placeholder?: string
  readonly?: boolean
}>()
</script>

<template>
  <textarea
    v-model="model"
    class="textarea textarea--code"
    spellcheck="false"
    :rows="rows || 8"
    :placeholder="placeholder"
    :readonly="readonly"
  ></textarea>
</template>
