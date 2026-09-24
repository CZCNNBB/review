<script setup lang="ts">
import { ElButton } from 'element-plus'

import AppDialog from '@/components/common/AppDialog.vue'
import CopyButton from '@/components/common/CopyButton.vue'

// 「生成调用示例」的结果窗。
// 旧版把命令拼进弹窗 HTML，复制按钮再靠 data-copy 拼一遍 —— 展示与复制是两份文本，
// 改一处忘一处就不一致。这里命令由调用方当数据传进来，两边共用同一份。
const open = defineModel<boolean>('open', { default: false })

const props = defineProps<{
  /** buildCurl 生成的完整命令 */
  command: string
}>()
</script>

<template>
  <AppDialog v-model:open="open" title="业务系统调用示例" width="720px">
    <pre class="raw-json">{{ props.command }}</pre>
    <template #footer>
      <ElButton @click="open = false">关闭</ElButton>
      <CopyButton :text="props.command" label="复制命令" />
    </template>
  </AppDialog>
</template>
