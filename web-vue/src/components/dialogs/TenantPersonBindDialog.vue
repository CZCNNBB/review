<script setup lang="ts">
import { ElButton } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { orgApi } from '@/api/modules/org'
import type { TenantPersonBinding } from '@/api/types'
import AppDialog from '@/components/common/AppDialog.vue'
import DynamicForm from '@/components/form/DynamicForm.vue'
import { errorMessageOf } from '@/composables/useConfirm'
import { usePersonDirectory } from '@/composables/usePersonDirectory'
import type { DynamicFieldSpec } from '@/utils/nodeConfigForm'
import { toastOk } from '@/utils/notify'

// 把全局人员绑到租户上，顺带记下他在业务系统里的工号与账号。
const open = defineModel<boolean>('open', { default: false })

const props = defineProps<{
  tenantId: string
}>()

const emit = defineEmits<{ (event: 'saved', binding: TenantPersonBinding): void }>()

// 人员候选走人员目录（带部门标签），不再由页面传 persons 进来
const directory = usePersonDirectory()

const fields = computed<DynamicFieldSpec[]>(() => [
  {
    name: 'person_id',
    label: '人员 *',
    type: 'person-select',
    required: true,
    options: directory.options.value,
  },
  {
    name: 'employee_no',
    label: '工号',
    type: 'text',
    hint: '租户内唯一，用于和业务系统的账号对齐',
  },
  {
    name: 'external_user_id',
    label: '外部用户标识',
    type: 'text',
    hint: '业务系统里的用户 ID，租户内唯一',
  },
  { name: 'display_name', label: '租户内显示名', type: 'text' },
])

const values = ref<Record<string, unknown>>({})
const error = ref('')
const submitting = ref(false)
const formRef = ref<InstanceType<typeof DynamicForm> | null>(null)

watch(open, (isOpen) => {
  if (!isOpen) return
  error.value = ''
  values.value = { person_id: '', employee_no: '', external_user_id: '', display_name: '' }
})

async function submit(): Promise<void> {
  if (!(await formRef.value?.validate())) return
  submitting.value = true
  error.value = ''
  // 空值统一送 null：工号这类字段留空表示「这个租户里没有」，不是空字符串
  const textOrNull = (value: unknown): string | null => String(value || '').trim() || null
  try {
    const created = await orgApi.bindTenantPerson(props.tenantId, {
      person_id: String(values.value.person_id || ''),
      employee_no: textOrNull(values.value.employee_no),
      external_user_id: textOrNull(values.value.external_user_id),
      display_name: textOrNull(values.value.display_name),
    })
    toastOk('绑定成功')
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
  <AppDialog v-model:open="open" title="绑定租户人员" width="620px">
    <DynamicForm ref="formRef" v-model="values" :fields="fields" :error="error" />
    <template #footer>
      <ElButton @click="open = false">取消</ElButton>
      <ElButton type="primary" :loading="submitting" @click="submit">绑定</ElButton>
    </template>
  </AppDialog>
</template>
