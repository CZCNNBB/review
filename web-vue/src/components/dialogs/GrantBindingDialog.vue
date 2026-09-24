<script setup lang="ts">
import { ElButton } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { grantApi } from '@/api/modules/grant'
import type { BusinessAction, Process, Tenant } from '@/api/types'
import AppDialog from '@/components/common/AppDialog.vue'
import DynamicForm from '@/components/form/DynamicForm.vue'
import { errorMessageOf } from '@/composables/useConfirm'
import type { DynamicFieldSpec } from '@/utils/nodeConfigForm'
import { toastOk } from '@/utils/notify'

// 授权租户使用审批流 / 业务动作。旧版是两个弹窗，字段只差被授权的资源，
// 这里用一个 mode 表达：选租户 + 选资源，提交到对应接口。
const open = defineModel<boolean>('open', { default: false })

const props = defineProps<{
  mode: 'process' | 'action'
  tenants: Tenant[]
  processes: Process[]
  actions: BusinessAction[]
}>()

const emit = defineEmits<{ (event: 'saved'): void }>()

const isProcess = computed(() => props.mode === 'process')
const values = ref<Record<string, unknown>>({})
const error = ref('')
const submitting = ref(false)
const formRef = ref<InstanceType<typeof DynamicForm> | null>(null)

const fields = computed<DynamicFieldSpec[]>(() => [
  {
    name: 'tenant_id',
    label: '租户 *',
    type: 'select',
    required: true,
    options: props.tenants.map((item) => ({ value: item.id, label: item.name })),
  },
  isProcess.value
    ? {
        name: 'process_id',
        label: '审批流 *',
        type: 'select',
        required: true,
        // 停用的流程仍能授权（老授权要能继续工作），但得让操作的人看得见
        options: props.processes.map((item) => ({
          value: item.id,
          label: `${item.name}${item.status === 'DISABLED' ? '（已停用）' : ''}`,
        })),
      }
    : {
        name: 'business_action_id',
        label: '业务动作 *',
        type: 'select',
        required: true,
        options: props.actions.map((item) => ({
          value: item.id,
          label: `${item.name}（${item.action_code}）`,
        })),
      },
])

watch(
  () => [open.value, props.mode] as const,
  ([isOpen]) => {
    if (!isOpen) return
    error.value = ''
    values.value = { tenant_id: '', process_id: '', business_action_id: '' }
  },
  { immediate: true },
)

async function submit(): Promise<void> {
  if (!(await formRef.value?.validate())) return
  submitting.value = true
  error.value = ''
  try {
    const tenantId = String(values.value.tenant_id)
    if (isProcess.value) {
      await grantApi.bindProcess(tenantId, { process_id: String(values.value.process_id) })
    } else {
      await grantApi.bindAction(tenantId, {
        business_action_id: String(values.value.business_action_id),
      })
    }
    toastOk('已授权')
    open.value = false
    emit('saved')
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
    :title="isProcess ? '授权租户使用审批流' : '授权租户使用业务动作'"
    width="600px"
  >
    <DynamicForm ref="formRef" v-model="values" :fields="fields" :error="error" />
    <template #footer>
      <ElButton @click="open = false">取消</ElButton>
      <ElButton type="primary" :loading="submitting" @click="submit">授权</ElButton>
    </template>
  </AppDialog>
</template>
