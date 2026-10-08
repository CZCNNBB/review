<script setup lang="ts">
import { ref } from 'vue'

import { fileApi } from '@/api/modules/file'
import type { ApprovalAttachment } from '@/api/types'
import { errorMessageOf } from '@/composables/useConfirm'
import { toastError } from '@/utils/notify'

defineProps<{ attachments: ApprovalAttachment[] }>()

const downloadingId = ref<string | null>(null)

/** 下载前走管理端鉴权；浏览器只接收授权后的文件内容。 */
async function download(attachment: ApprovalAttachment): Promise<void> {
  downloadingId.value = attachment.file_id
  try {
    const blob = await fileApi.download(attachment.file_id)
    const objectUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = attachment.file_name
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
  } catch (error) {
    toastError(errorMessageOf(error))
  } finally {
    downloadingId.value = null
  }
}
</script>

<template>
  <ul class="approval-attachments">
    <li v-for="attachment in attachments" :key="attachment.file_id">
      <div>
        <strong>{{ attachment.file_name }}</strong>
        <span>{{ (attachment.size_bytes / 1024).toFixed(1) }} KiB</span>
      </div>
      <button
        class="btn btn--sm"
        type="button"
        :disabled="downloadingId === attachment.file_id"
        @click="download(attachment)"
      >
        {{ downloadingId === attachment.file_id ? '下载中…' : '下载' }}
      </button>
    </li>
  </ul>
</template>

<style scoped>
.approval-attachments {
  display: grid;
  gap: var(--sp-3);
  margin: 0;
  padding: 0;
  list-style: none;
}
.approval-attachments li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-4);
  padding: var(--sp-3);
  border: 1px solid var(--rule-weak);
  border-radius: var(--radius-md);
}
.approval-attachments li > div {
  display: grid;
  min-width: 0;
  gap: var(--sp-1);
}
.approval-attachments strong {
  overflow-wrap: anywhere;
}
.approval-attachments span {
  color: var(--ink-3);
  font-size: var(--fs-sm);
}
</style>
