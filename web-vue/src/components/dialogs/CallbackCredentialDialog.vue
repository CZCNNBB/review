<script setup lang="ts">
import { ElButton } from 'element-plus'
import { ref, watch } from 'vue'

import { tenantApi } from '@/api/modules/tenant'
import type { CallbackCredential } from '@/api/types'
import AppDialog from '@/components/common/AppDialog.vue'
import DynamicForm from '@/components/form/DynamicForm.vue'
import { errorMessageOf } from '@/composables/useConfirm'
import type { DynamicFieldSpec } from '@/utils/nodeConfigForm'
import { toastOk } from '@/utils/notify'

// 配置回调 Service Token。Token 由业务系统自己签发，审批中心只加密保存，
// 因此这里只有「配置」没有「查看」：列表永远只回显元数据。
const open = defineModel<boolean>('open', { default: false })

const props = defineProps<{
  tenantId: string
}>()

const emit = defineEmits<{ (event: 'saved', credential: CallbackCredential): void }>()

const fields: DynamicFieldSpec[] = [
  {
    name: 'name',
    label: '用途名称 *',
    type: 'text',
    required: true,
    placeholder: '审批中心服务账号',
  },
  {
    name: 'token',
    label: 'Service Token *',
    type: 'text',
    required: true,
    hint: '由业务系统为自己的服务账号签发，审批中心加密保存且不回显明文',
  },
  { name: 'header_name', label: '认证请求头', type: 'text', placeholder: 'Authorization' },
  {
    name: 'token_prefix',
    label: 'Token 前缀',
    type: 'text',
    placeholder: 'Bearer',
    hint: '留空表示请求头里直接放 Token 明文',
  },
  { name: 'expires_at', label: '过期时间', type: 'text', placeholder: '留空表示长期有效' },
]

const values = ref<Record<string, unknown>>({})
const error = ref('')
const submitting = ref(false)
const formRef = ref<InstanceType<typeof DynamicForm> | null>(null)

watch(open, (isOpen) => {
  if (!isOpen) return
  error.value = ''
  // 默认值沿用旧版：认证头 Authorization、前缀 Bearer，只改用途名称和 Token 就能存
  values.value = {
    name: '',
    token: '',
    header_name: 'Authorization',
    token_prefix: 'Bearer',
    expires_at: '',
  }
})

async function submit(): Promise<void> {
  if (!(await formRef.value?.validate())) return
  submitting.value = true
  error.value = ''
  const tokenPrefix = values.value.token_prefix
  try {
    const created = await tenantApi.createCredential(props.tenantId, {
      name: String(values.value.name || '').trim(),
      token: String(values.value.token || '').trim(),
      header_name: String(values.value.header_name || '').trim() || 'Authorization',
      // 空字符串是有意义的取值（认证头里直接放明文），不能像别的字段那样兜底成默认值
      token_prefix:
        tokenPrefix === '' || tokenPrefix === null || tokenPrefix === undefined
          ? ''
          : String(tokenPrefix).trim(),
      expires_at: String(values.value.expires_at || '').trim() || null,
    })
    toastOk('回调凭据已保存')
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
  <AppDialog v-model:open="open" title="配置回调 Service Token" width="620px">
    <DynamicForm ref="formRef" v-model="values" :fields="fields" :error="error" />
    <template #footer>
      <ElButton @click="open = false">取消</ElButton>
      <ElButton type="primary" :loading="submitting" @click="submit">保存凭据</ElButton>
    </template>
  </AppDialog>
</template>
