<script setup lang="ts">
import { ElButton } from 'element-plus'
import { ref, watch } from 'vue'

import { orgApi } from '@/api/modules/org'
import type { Department } from '@/api/types'
import AppDialog from '@/components/common/AppDialog.vue'
import DynamicForm from '@/components/form/DynamicForm.vue'
import { errorMessageOf } from '@/composables/useConfirm'
import type { DynamicFieldSpec } from '@/utils/nodeConfigForm'
import { toastOk } from '@/utils/notify'

// 新建部门。后端没有改名之外的编辑入口，第一版也只放新建（与旧版一致）。
const open = defineModel<boolean>('open', { default: false })

const emit = defineEmits<{ (event: 'saved', department: Department): void }>()

const fields: DynamicFieldSpec[] = [
  {
    name: 'code',
    label: '部门编码 *',
    type: 'text',
    required: true,
    placeholder: 'FINANCE',
    hint: '字母开头，字母数字下划线，保存时统一转大写',
  },
  { name: 'name', label: '部门名称 *', type: 'text', required: true, placeholder: '财务部' },
]

const values = ref<Record<string, unknown>>({})
const error = ref('')
const submitting = ref(false)
const formRef = ref<InstanceType<typeof DynamicForm> | null>(null)

watch(open, (isOpen) => {
  if (!isOpen) return
  error.value = ''
  values.value = { code: '', name: '' }
})

async function submit(): Promise<void> {
  if (!(await formRef.value?.validate())) return
  submitting.value = true
  error.value = ''
  try {
    const created = await orgApi.createDepartment({
      code: String(values.value.code || '').trim(),
      name: String(values.value.name || '').trim(),
    })
    toastOk('部门已创建')
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
  <AppDialog v-model:open="open" title="新建部门" width="620px">
    <DynamicForm ref="formRef" v-model="values" :fields="fields" :error="error" />
    <template #footer>
      <ElButton @click="open = false">取消</ElButton>
      <ElButton type="primary" :loading="submitting" @click="submit">创建</ElButton>
    </template>
  </AppDialog>
</template>
