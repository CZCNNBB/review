<script setup lang="ts">
import { ElButton } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { orgApi } from '@/api/modules/org'
import type { Person } from '@/api/types'
import AppDialog from '@/components/common/AppDialog.vue'
import DynamicForm from '@/components/form/DynamicForm.vue'
import { errorMessageOf } from '@/composables/useConfirm'
import type { DynamicFieldSpec } from '@/utils/nodeConfigForm'
import { toastOk } from '@/utils/notify'

// 新建 / 编辑人员。与旧版一致：状态只在编辑时出现 —— 新建的人一定是启用态，
// 旧版创建接口也不接受 status。
const open = defineModel<boolean>('open', { default: false })

const props = defineProps<{
  /** 传了就是编辑，不传就是新建 */
  person?: Person | null
}>()

const emit = defineEmits<{ (event: 'saved', person: Person): void }>()

const isNew = computed(() => !props.person)

const fields = computed<DynamicFieldSpec[]>(() => [
  { name: 'name', label: '姓名 *', type: 'text', required: true },
  { name: 'mobile', label: '手机号', type: 'text' },
  { name: 'email', label: '邮箱', type: 'text' },
  ...(isNew.value
    ? []
    : [
        {
          name: 'status',
          label: '状态',
          type: 'select' as const,
          options: [
            { value: 'ENABLED', label: '启用' },
            { value: 'DISABLED', label: '停用' },
          ],
          hint: '停用后不能再作为新审批流的审批人',
        },
      ]),
])

const values = ref<Record<string, unknown>>({})
const error = ref('')
const submitting = ref(false)
const formRef = ref<InstanceType<typeof DynamicForm> | null>(null)

watch(
  () => [open.value, props.person] as const,
  ([isOpen]) => {
    if (!isOpen) return
    error.value = ''
    values.value = props.person
      ? {
          name: props.person.name,
          mobile: props.person.mobile || '',
          email: props.person.email || '',
          status: props.person.status,
        }
      : { name: '', mobile: '', email: '' }
  },
  { immediate: true },
)

async function submit(): Promise<void> {
  if (!(await formRef.value?.validate())) return
  submitting.value = true
  error.value = ''
  // 空字符串由后端统一规整成 null，这里不做第二套口径
  const payload = {
    name: String(values.value.name || '').trim(),
    mobile: String(values.value.mobile || '').trim(),
    email: String(values.value.email || '').trim(),
  }
  try {
    const saved = props.person
      ? await orgApi.updatePerson(props.person.id, {
          ...payload,
          status: String(values.value.status),
        })
      : await orgApi.createPerson(payload)
    toastOk(props.person ? '人员已更新' : '人员已创建')
    open.value = false
    emit('saved', saved)
  } catch (err) {
    error.value = errorMessageOf(err)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AppDialog v-model:open="open" :title="isNew ? '新建人员' : '编辑人员'" width="620px">
    <DynamicForm ref="formRef" v-model="values" :fields="fields" :error="error" />
    <template #footer>
      <ElButton @click="open = false">取消</ElButton>
      <ElButton type="primary" :loading="submitting" @click="submit">
        {{ isNew ? '创建' : '保存' }}
      </ElButton>
    </template>
  </AppDialog>
</template>
