<script setup lang="ts">
import { ElButton } from 'element-plus'
import { ref, watch } from 'vue'

import { processApi } from '@/api/modules/process'
import type { Process } from '@/api/types'
import AppDialog from '@/components/common/AppDialog.vue'
import DynamicForm from '@/components/form/DynamicForm.vue'
import { errorMessageOf } from '@/composables/useConfirm'
import type { DynamicFieldSpec } from '@/utils/nodeConfigForm'
import { toastOk } from '@/utils/notify'

// 新建审批流。旧版是 formDialog(名称 + 说明)，提交后由页面跳进 V1 草稿的编排页；
// 这里保持同一分工：弹窗只负责建，跳到哪一页由调用方决定。
const open = defineModel<boolean>('open', { default: false })

const emit = defineEmits<{ (event: 'saved', process: Process): void }>()

const fields: DynamicFieldSpec[] = [
  { name: 'name', label: '流程名称 *', type: 'text', required: true, placeholder: '付款审批流程' },
  {
    name: 'description',
    label: '流程说明',
    type: 'text',
    hint: '创建后会进入编排页，在那里添加节点、审批人和表单字段',
  },
]

const values = ref<Record<string, unknown>>({})
const error = ref('')
const submitting = ref(false)
const formRef = ref<InstanceType<typeof DynamicForm> | null>(null)

// 弹窗组件是常驻的，每次打开都要回到空白状态，否则会带上一次的输入
watch(open, (isOpen) => {
  if (!isOpen) return
  error.value = ''
  values.value = { name: '', description: '' }
})

async function submit(): Promise<void> {
  if (!(await formRef.value?.validate())) return
  submitting.value = true
  error.value = ''
  try {
    const created = await processApi.create({
      name: String(values.value.name || '').trim(),
      description: String(values.value.description || '').trim() || null,
    })
    toastOk('审批流已创建，接下来编辑 V1 草稿')
    open.value = false
    emit('saved', created)
  } catch (err) {
    error.value = errorMessageOf(err)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AppDialog v-model:open="open" title="新建审批流" width="620px">
    <DynamicForm ref="formRef" v-model="values" :fields="fields" :error="error" />
    <template #footer>
      <ElButton @click="open = false">取消</ElButton>
      <ElButton type="primary" :loading="submitting" @click="submit">创建并进入编排</ElButton>
    </template>
  </AppDialog>
</template>
