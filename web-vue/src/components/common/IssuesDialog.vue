<script setup lang="ts">
import { ElButton } from 'element-plus'
import { computed } from 'vue'

import AppDialog from '@/components/common/AppDialog.vue'
import type { ValidationIssue } from '@/types/domain'
import { shortId } from '@/utils/format'

// 校验结果弹窗。对应旧版 showIssues(title, issues)：
// 每条问题显示规则码 + 文案，后面缀上节点/字段/连线位置，便于定位。
const open = defineModel<boolean>('open', { default: false })

const props = defineProps<{
  title: string
  issues: ValidationIssue[]
}>()

const items = computed(() =>
  props.issues.map((issue) => ({
    code: issue.code,
    message: issue.message,
    where: [
      issue.node_id ? `节点 ${shortId(issue.node_id)}` : '',
      issue.field ? `字段 ${issue.field}` : '',
      issue.connection_index === null || issue.connection_index === undefined
        ? ''
        : `连线 #${issue.connection_index}`,
    ]
      .filter(Boolean)
      .join(' · '),
  })),
)
</script>

<template>
  <AppDialog v-model:open="open" :title="props.title" width="720px">
    <div v-if="!items.length" class="note note--ok">没有发现问题，可以发布。</div>
    <ul v-else class="issue-list">
      <li v-for="(item, index) in items" :key="index" class="issue">
        <span class="issue__code">{{ item.code }}</span>
        <span class="issue__message">{{ item.message }}</span>
        <span v-if="item.where" class="issue__where">{{ item.where }}</span>
      </li>
    </ul>
    <template #footer>
      <ElButton @click="open = false">关闭</ElButton>
    </template>
  </AppDialog>
</template>
