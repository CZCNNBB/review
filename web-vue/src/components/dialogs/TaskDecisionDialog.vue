<script lang="ts">
/**
 * 同意/拒绝之后接口返回的最新状态。后端是 ApprovalActionResponse，
 * 接口层把返回值声明成了 unknown（两个页面用的字段不同），这里补上页面用得着的那部分。
 */
export interface TaskDecisionResult {
  instance_id?: string | null
  instance_status?: string | null
}
</script>

<script setup lang="ts">
import { ElButton } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { approvalApi } from '@/api/modules/approval'
import AppDialog from '@/components/common/AppDialog.vue'
import DynamicForm from '@/components/form/DynamicForm.vue'
import { errorMessageOf } from '@/composables/useConfirm'
import { useCredentialsStore } from '@/stores/credentials'
import type { DynamicFieldSpec } from '@/utils/nodeConfigForm'

// 同意与拒绝共用一个弹窗：标题、按钮文案和提交的接口都由 kind 决定。
// 旧版是 formDialog + 各页面里的 handleTask(taskId, kind) 各写一遍，这里收成一处。
const open = defineModel<boolean>('open', { default: false })

const props = defineProps<{
  kind: 'approve' | 'reject'
  /** 要处理的任务。person_id 取任务所属审批人 —— 管理台没有登录身份，代为处理 */
  task?: { id: string; approver_person_id: string } | null
  /** 任务所属审批人的姓名，拼进标题（旧版 personNameOf 的展示口径） */
  approverName: string
}>()

const emit = defineEmits<{ (event: 'decided', result: TaskDecisionResult): void }>()

const credentials = useCredentialsStore()
const values = ref<Record<string, unknown>>({})
const error = ref('')
const submitting = ref(false)

const isApprove = computed(() => props.kind === 'approve')

const fields = computed<DynamicFieldSpec[]>(() => [
  {
    name: 'comment',
    label: '审批意见',
    type: 'textarea',
    wide: true,
    // 同意与拒绝用不同的占位文案，把意见往不同方向带（旧版同此）
    placeholder: isApprove.value ? '同意，按合同付款。' : '请说明拒绝的原因。',
  },
])

watch(open, (isOpen) => {
  // 每次打开都是一次新的处理：清掉上一条的意见和上次的报错
  if (!isOpen) return
  error.value = ''
  values.value = { comment: '' }
})

async function submit(): Promise<void> {
  if (!props.task) {
    // 列表刷新后任务可能已经不在了（旧版这里直接抛错，改为就地提示）
    error.value = '任务已刷新，请重新加载页面'
    return
  }
  submitting.value = true
  error.value = ''
  const body = {
    person_id: props.task.approver_person_id,
    comment: String(values.value.comment || '').trim() || null,
  }
  try {
    const result = isApprove.value
      ? await approvalApi.approve(props.task.id, body)
      : await approvalApi.reject(props.task.id, body)
    // 任务状态变了：租户密钥借用与使用记录缓存立刻失效（旧版 invalidateTenantCache）
    credentials.invalidate()
    open.value = false
    emit('decided', result as TaskDecisionResult)
  } catch (err) {
    error.value = errorMessageOf(err)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AppDialog
    v-model:open="open"
    :title="`${isApprove ? '同意' : '拒绝'}审批 · ${props.approverName}`"
    width="620px"
  >
    <DynamicForm v-model="values" :fields="fields" :error="error" />

    <template #footer>
      <ElButton @click="open = false">取消</ElButton>
      <ElButton type="primary" :loading="submitting" @click="submit">
        {{ isApprove ? '同意' : '拒绝' }}
      </ElButton>
    </template>
  </AppDialog>
</template>
