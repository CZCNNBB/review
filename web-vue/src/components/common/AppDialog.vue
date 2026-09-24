<script setup lang="ts">
import { ElDialog } from 'element-plus'

// 弹窗壳。录入件统一走 Element Plus，页面里不再直接出现 <el-dialog>。
// 结构对应旧版 dialogShell：标题 + 内容（自带滚动）+ 底部按钮区。
const open = defineModel<boolean>('open', { default: false })

const props = defineProps<{
  title: string
  width?: string
  /** 关闭前拦截：返回 false 可以阻止关闭（例如有未保存内容） */
  beforeClose?: () => boolean
}>()

function handleClose(done: () => void): void {
  if (props.beforeClose && !props.beforeClose()) return
  done()
}
</script>

<template>
  <ElDialog
    v-model="open"
    :title="props.title"
    :width="props.width || '640px'"
    append-to-body
    destroy-on-close
    :before-close="handleClose"
  >
    <div class="dialog__body">
      <slot />
    </div>
    <template #footer>
      <slot name="footer" />
    </template>
  </ElDialog>
</template>

<style scoped>
/* 弹窗内容自己有滚动条，长表单不会把按钮顶出屏幕 */
.dialog__body {
  max-height: 62vh;
  overflow-y: auto;
}
</style>
