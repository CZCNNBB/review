<script setup lang="ts">
import { ElButton } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { tenantApi } from '@/api/modules/tenant'
import type { Tenant } from '@/api/types'
import AppDialog from '@/components/common/AppDialog.vue'
import DynamicForm from '@/components/form/DynamicForm.vue'
import { errorMessageOf } from '@/composables/useConfirm'
import type { DynamicFieldSpec } from '@/utils/nodeConfigForm'
import { toastOk } from '@/utils/notify'

// 新建 / 编辑租户。旧版新建与编辑是两个弹窗，字段只在有没有 code 上不同，
// 这里合成一个：code 只在新建时可填，其余字段共用。
const open = defineModel<boolean>('open', { default: false })

const props = defineProps<{
  /** 传了就是编辑，不传就是新建 */
  tenant?: Tenant | null
}>()

const emit = defineEmits<{ (event: 'saved', tenant: Tenant): void }>()

const isNew = computed(() => !props.tenant)
const values = ref<Record<string, unknown>>({})
const error = ref('')
const submitting = ref(false)
const formRef = ref<InstanceType<typeof DynamicForm> | null>(null)

const fields = computed<DynamicFieldSpec[]>(() => [
  ...(isNew.value
    ? [
        {
          name: 'code',
          label: '租户编码 *',
          type: 'text' as const,
          required: true,
          placeholder: 'PAYMENT',
          hint: '大写字母开头，字母数字下划线，创建后不可修改',
        },
      ]
    : []),
  { name: 'name', label: '租户名称 *', type: 'text', required: true, placeholder: '付款系统' },
  {
    name: 'callback_base_url',
    label: '回调基础地址 *',
    type: 'text',
    required: true,
    placeholder: 'https://payment.example.com',
    hint: '审批通过后回调业务系统时使用，只填到域名',
  },
  { name: 'description', label: '说明', type: 'textarea', wide: true },
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
        },
      ]),
])

watch(
  () => [open.value, props.tenant] as const,
  ([isOpen]) => {
    if (!isOpen) return
    error.value = ''
    values.value = props.tenant
      ? {
          name: props.tenant.name,
          callback_base_url: props.tenant.callback_base_url,
          description: props.tenant.description || '',
          status: props.tenant.status,
        }
      : { name: '', callback_base_url: '', description: '', status: 'ENABLED' }
  },
  { immediate: true },
)

async function submit(): Promise<void> {
  if (!(await formRef.value?.validate())) return
  submitting.value = true
  error.value = ''
  const payload = {
    name: String(values.value.name || '').trim(),
    callback_base_url: String(values.value.callback_base_url || '').trim(),
    description: String(values.value.description || '').trim() || null,
  }
  try {
    const saved = props.tenant
      ? await tenantApi.update(props.tenant.id, { ...payload, status: String(values.value.status) })
      : await tenantApi.create({ ...payload, code: String(values.value.code || '').trim() })
    toastOk(props.tenant ? '租户已更新' : '租户已创建')
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
  <AppDialog v-model:open="open" :title="isNew ? '新建租户' : '编辑租户'" width="620px">
    <DynamicForm ref="formRef" v-model="values" :fields="fields" :error="error" />
    <template #footer>
      <ElButton @click="open = false">取消</ElButton>
      <ElButton type="primary" :loading="submitting" @click="submit">
        {{ isNew ? '创建' : '保存' }}
      </ElButton>
    </template>
  </AppDialog>
</template>
