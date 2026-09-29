<script setup lang="ts">
import PanelCard from '@/components/layout/PanelCard.vue'

/** 审批与抄送详情共用的正文层级：表单、流转记录、补充内容、技术信息。 */
defineSlots<{
  form: () => unknown
  timeline: () => unknown
  extra?: () => unknown
  metadata: () => unknown
}>()
</script>

<template>
  <div class="detail-sections">
    <div class="detail-sections__main">
      <PanelCard title="审批表单"><slot name="form" /></PanelCard>
      <PanelCard title="流转节点与审批意见"><slot name="timeline" /></PanelCard>
    </div>

    <div v-if="$slots.extra" class="detail-sections__extra">
      <slot name="extra" />
    </div>

    <details class="detail-sections__meta">
      <summary>查看审批单技术信息</summary>
      <div class="detail-sections__meta-body">
        <slot name="metadata" />
      </div>
    </details>
  </div>
</template>

<style scoped>
/* 表单优先占主要阅读宽度，窄屏按表单、流转记录的顺序堆叠。 */
.detail-sections__main {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(360px, 0.85fr);
  align-items: start;
  gap: var(--sp-5);
}
.detail-sections__main :deep(.panel + .panel) {
  margin-top: 0;
}
.detail-sections__main :deep(.panel) {
  min-width: 0;
}
.detail-sections__extra {
  margin-top: var(--sp-5);
}
/* 技术字段保留可查，但默认不与审批表单争夺首屏位置。 */
.detail-sections__meta {
  margin-top: var(--sp-5);
  border: 1px solid var(--rule);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.detail-sections__meta summary {
  padding: var(--sp-4);
  color: var(--ink-2);
  font-size: var(--fs-md);
  font-weight: 600;
  cursor: pointer;
}
.detail-sections__meta summary:hover {
  color: var(--indigo);
}
.detail-sections__meta-body {
  padding: var(--sp-4);
  border-top: 1px solid var(--rule-weak);
}
@media (max-width: 1180px) {
  .detail-sections__main {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
