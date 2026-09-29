<script setup lang="ts">
import StatusStamp from '@/components/common/StatusStamp.vue'

/** 审批与抄送详情共用的摘要区：先呈现身份、状态和当前事项。 */
defineProps<{
  kind: 'APPROVAL' | 'COPY'
  title: string
  status: string
  businessKey: string
  processLabel: string
  currentNodeName: string | null
  applicantName: string
  startedAt: string
  duration: string
  recipientName?: string
  pendingCount?: number
}>()
</script>

<template>
  <section class="detail-hero" aria-label="审批单概览">
    <div class="detail-hero__top">
      <div class="detail-hero__identity">
        <div class="detail-hero__kind" :class="kind === 'COPY' ? 'detail-hero__kind--copy' : ''">
          {{ kind === 'COPY' ? '抄送记录 · 只读' : '审批详情' }}
        </div>
        <h1 class="detail-hero__title">{{ title }}</h1>
        <p class="detail-hero__subtitle">业务单号 {{ businessKey }} · {{ processLabel }}</p>
      </div>
      <StatusStamp :status="status" />
    </div>

    <div class="detail-hero__focus" :class="kind === 'COPY' ? 'detail-hero__focus--copy' : ''">
      <span class="detail-hero__focus-label">{{ kind === 'COPY' ? '查看权限' : '当前进度' }}</span>
      <div>
        <strong v-if="kind === 'COPY'">这张审批单已抄送给 {{ recipientName || '指定收件人' }}</strong>
        <strong v-else>{{
          currentNodeName ? `正在「${currentNodeName}」处理` : '流程已结束'
        }}</strong>
        <p v-if="kind === 'COPY'">
          {{
            currentNodeName ? `当前位于「${currentNodeName}」；` : ''
          }}可查看表单、流转节点和审批意见，无需处理。
        </p>
        <p v-else-if="pendingCount">下方有 {{ pendingCount }} 条审批待办可处理。</p>
        <p v-else>可查看审批表单与完整流转记录。</p>
      </div>
    </div>

    <dl class="detail-hero__facts" :class="kind === 'COPY' ? 'detail-hero__facts--copy' : ''">
      <div>
        <dt>发起人</dt>
        <dd>{{ applicantName }}</dd>
      </div>
      <div v-if="kind === 'COPY'">
        <dt>抄送给</dt>
        <dd>{{ recipientName || '—' }}</dd>
      </div>
      <div>
        <dt>发起时间</dt>
        <dd>{{ startedAt }}</dd>
      </div>
      <div>
        <dt>已用时</dt>
        <dd>{{ duration }}</dd>
      </div>
    </dl>
  </section>
</template>

<style scoped>
/* 概览区比普通资料卡更醒目，但继续使用项目既有色彩与边框。 */
.detail-hero {
  margin-bottom: var(--sp-5);
  padding: var(--sp-6);
  border: 1px solid var(--indigo-line);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.detail-hero__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-5);
}
.detail-hero__identity {
  min-width: 0;
}
.detail-hero__kind {
  color: var(--indigo);
  font-size: var(--fs-xs);
  font-weight: 700;
  letter-spacing: 0.08em;
}
.detail-hero__kind--copy {
  color: var(--pine);
}
.detail-hero__title {
  margin-top: var(--sp-2);
  font-size: 24px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}
.detail-hero__subtitle {
  margin: var(--sp-2) 0 0;
  color: var(--ink-2);
  font-size: var(--fs-md);
  overflow-wrap: anywhere;
}
.detail-hero__focus {
  display: flex;
  gap: var(--sp-5);
  margin-top: var(--sp-6);
  padding: var(--sp-4);
  border-left: 3px solid var(--indigo);
  background: var(--indigo-wash);
}
.detail-hero__focus--copy {
  border-left-color: var(--pine);
  background: var(--pine-wash);
}
.detail-hero__focus-label {
  flex: 0 0 64px;
  color: var(--ink-2);
  font-size: var(--fs-sm);
}
.detail-hero__focus strong {
  display: block;
  font-size: var(--fs-lg);
}
.detail-hero__focus p {
  margin: var(--sp-1) 0 0;
  color: var(--ink-2);
  font-size: var(--fs-md);
}
.detail-hero__facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--sp-4);
  margin: var(--sp-5) 0 0;
}
.detail-hero__facts--copy {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}
.detail-hero__facts dt {
  color: var(--ink-3);
  font-size: var(--fs-sm);
}
.detail-hero__facts dd {
  margin: var(--sp-1) 0 0;
  font-size: var(--fs-base);
  font-weight: 600;
  overflow-wrap: anywhere;
}
@media (max-width: 700px) {
  .detail-hero {
    padding: var(--sp-4);
  }
  .detail-hero__top {
    flex-wrap: wrap;
  }
  .detail-hero__title {
    font-size: var(--fs-title);
  }
  .detail-hero__focus {
    display: block;
  }
  .detail-hero__focus-label {
    display: block;
    margin-bottom: var(--sp-1);
  }
  .detail-hero__facts,
  .detail-hero__facts--copy {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
