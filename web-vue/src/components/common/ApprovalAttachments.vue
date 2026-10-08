<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'

import { fileApi } from '@/api/modules/file'
import type { ApprovalAttachment } from '@/api/types'
import { errorMessageOf } from '@/composables/useConfirm'
import { toastError } from '@/utils/notify'
import AppDialog from '@/components/common/AppDialog.vue'

defineProps<{ attachments: ApprovalAttachment[] }>()

const downloadingId = ref<string | null>(null)
const previewOpen = ref(false)
const previewAttachment = ref<ApprovalAttachment | null>(null)
const previewUrl = ref('')
const previewLoading = ref(false)
const previewError = ref('')
const imageZoom = ref(100)
let previewRequest = 0

/** 仅预览当前支持的图片和 PDF，不按扩展名把其他内容嵌入页面。 */
function previewType(attachment: ApprovalAttachment): 'image' | 'pdf' | null {
  const contentType = attachment.content_type.toLowerCase().split(';')[0]?.trim()
  if (contentType === 'image/png' || contentType === 'image/jpeg') return 'image'
  if (contentType === 'application/pdf') return 'pdf'
  return null
}

/** 释放本地文件 URL，避免关闭弹窗后大文件继续占用内存。 */
function releasePreview(): void {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
}

/** 关闭时使未完成请求失效，防止旧附件在下一次打开时覆盖新内容。 */
function clearPreview(): void {
  previewRequest += 1
  releasePreview()
  previewAttachment.value = null
  previewLoading.value = false
  previewError.value = ''
}

/** 复用已鉴权的文件内容接口，下载到本地 Blob 后在平台弹窗中展示。 */
async function preview(attachment: ApprovalAttachment): Promise<void> {
  if (!previewType(attachment)) return
  const request = ++previewRequest
  releasePreview()
  previewAttachment.value = attachment
  previewOpen.value = true
  previewLoading.value = true
  previewError.value = ''
  imageZoom.value = 100
  try {
    const blob = await fileApi.download(attachment.file_id)
    // 用户可能已关闭或切换附件；过期响应不创建 URL，也不改变当前弹窗状态。
    if (request !== previewRequest) return
    previewUrl.value = URL.createObjectURL(blob)
  } catch (error) {
    if (request === previewRequest) previewError.value = errorMessageOf(error)
  } finally {
    if (request === previewRequest) previewLoading.value = false
  }
}

/** 图片加载失败时显示操作提示，保留下载与重试入口。 */
function handleImageError(): void {
  previewError.value = '图片无法显示，请重试或下载原文件查看。'
}

/** 限制图片缩放范围，放大后可在预览区域内滚动查看。 */
function changeZoom(step: number): void {
  imageZoom.value = Math.min(300, Math.max(25, imageZoom.value + step))
}

/** 弹窗通过关闭按钮、遮罩或 Escape 关闭时统一清理附件状态。 */
watch(
  previewOpen,
  (open) => {
    if (!open) clearPreview()
  },
  { flush: 'sync' },
)
onBeforeUnmount(clearPreview)

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
      <div class="attachment-info">
        <strong>{{ attachment.file_name }}</strong>
        <span>{{ (attachment.size_bytes / 1024).toFixed(1) }} KiB</span>
      </div>
      <div class="attachment-actions">
        <button
          v-if="previewType(attachment)"
          class="btn btn--sm"
          type="button"
          @click="preview(attachment)"
        >
          预览
        </button>
        <span v-else class="attachment-hint">此格式请下载查看</span>
        <button
          class="btn btn--sm"
          type="button"
          :disabled="downloadingId === attachment.file_id"
          @click="download(attachment)"
        >
          {{ downloadingId === attachment.file_id ? '下载中…' : '下载' }}
        </button>
      </div>
    </li>
  </ul>

  <AppDialog
    v-model:open="previewOpen"
    :title="`附件预览 · ${previewAttachment?.file_name || ''}`"
    width="min(1100px, 94vw)"
  >
    <div v-if="previewLoading" class="preview-message" role="status">正在加载附件…</div>
    <div v-else-if="previewError" class="preview-message" role="alert">
      <p>{{ previewError }}</p>
      <button v-if="previewAttachment" class="btn btn--sm" @click="preview(previewAttachment)">
        重试
      </button>
    </div>
    <template v-else-if="previewAttachment && previewUrl">
      <template v-if="previewType(previewAttachment) === 'image'">
        <div class="preview-toolbar" aria-label="图片缩放">
          <button class="btn btn--sm" :disabled="imageZoom <= 25" @click="changeZoom(-25)">
            缩小
          </button>
          <span>{{ imageZoom }}%</span>
          <button class="btn btn--sm" :disabled="imageZoom >= 300" @click="changeZoom(25)">
            放大
          </button>
          <button class="btn btn--sm" @click="imageZoom = 100">重置</button>
        </div>
        <div class="preview-image-canvas">
          <img
            :src="previewUrl"
            :alt="previewAttachment.file_name"
            :style="{ width: `${imageZoom}%` }"
            @error="handleImageError"
          />
        </div>
      </template>
      <iframe
        v-else
        class="preview-pdf"
        :src="previewUrl"
        :title="`PDF 预览：${previewAttachment.file_name}`"
      />
    </template>
    <template #footer>
      <div class="preview-footer">
        <a
          v-if="previewUrl && !previewError"
          class="btn btn--sm"
          :href="previewUrl"
          target="_blank"
          rel="noopener noreferrer"
        >
          新窗口打开
        </a>
        <button
          v-if="previewAttachment"
          class="btn btn--sm"
          :disabled="downloadingId === previewAttachment.file_id"
          @click="download(previewAttachment)"
        >
          下载原文件
        </button>
        <button class="btn btn--sm" @click="previewOpen = false">关闭</button>
      </div>
    </template>
  </AppDialog>
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
.attachment-info {
  display: grid;
  min-width: 0;
  gap: var(--sp-1);
}
.attachment-actions,
.preview-toolbar,
.preview-footer {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex-wrap: wrap;
}
.attachment-actions {
  justify-content: flex-end;
  flex-shrink: 0;
}
.attachment-hint {
  font-size: var(--fs-sm);
  color: var(--ink-3);
}
.preview-toolbar {
  margin-bottom: var(--sp-3);
}
.preview-footer {
  justify-content: flex-end;
}
.preview-message {
  padding: var(--sp-6);
  text-align: center;
}
.preview-image-canvas {
  max-height: 50vh;
  overflow: auto;
  background: var(--sunken);
}
.preview-image-canvas img {
  display: block;
  margin: 0 auto;
  height: auto;
}
.preview-pdf {
  display: block;
  width: 100%;
  height: 58vh;
  border: 0;
}
@media (max-width: 640px) {
  .approval-attachments li {
    align-items: flex-start;
    flex-direction: column;
  }
}
.approval-attachments strong {
  overflow-wrap: anywhere;
}
.approval-attachments span {
  color: var(--ink-3);
  font-size: var(--fs-sm);
}
</style>
