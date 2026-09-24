<script setup lang="ts">
import { ElButton } from 'element-plus'
import { ref, watch } from 'vue'

import { tenantApi } from '@/api/modules/tenant'
import type { TenantApiKey } from '@/api/types'
import AppDialog from '@/components/common/AppDialog.vue'
import CopyButton from '@/components/common/CopyButton.vue'
import DynamicForm from '@/components/form/DynamicForm.vue'
import { errorMessageOf } from '@/composables/useConfirm'
import type { DynamicFieldSpec } from '@/utils/nodeConfigForm'
import { toastOk } from '@/utils/notify'

// 签发租户 API Key。明文只在签发这一刻由接口返回，所以成功后不立刻关窗，
// 改为把明文留在眼前让用户自己复制：旧版是签发后抢一次自动复制，复制失败或
// 提示没看见，这把密钥就找不回来了（列表接口不回显明文）。
const open = defineModel<boolean>('open', { default: false })

const props = defineProps<{
  tenantId: string
}>()

const emit = defineEmits<{ (event: 'saved', apiKey: TenantApiKey): void }>()

const fields: DynamicFieldSpec[] = [
  {
    name: 'name',
    label: '用途名称 *',
    type: 'text',
    required: true,
    placeholder: '付款系统生产环境',
  },
  {
    name: 'expires_at',
    label: '过期时间',
    type: 'text',
    placeholder: '留空表示长期有效，例如 2026-12-31T00:00:00Z',
  },
]

const values = ref<Record<string, unknown>>({})
const error = ref('')
const submitting = ref(false)
/** 签发成功后的明文，非空时弹窗切换成「复制密钥」形态 */
const issued = ref<TenantApiKey | null>(null)
const formRef = ref<InstanceType<typeof DynamicForm> | null>(null)

watch(open, (isOpen) => {
  if (!isOpen) return
  error.value = ''
  issued.value = null
  values.value = { name: '', expires_at: '' }
})

async function submit(): Promise<void> {
  if (!(await formRef.value?.validate())) return
  submitting.value = true
  error.value = ''
  try {
    const created = await tenantApi.issueApiKey(props.tenantId, {
      name: String(values.value.name || '').trim(),
      expires_at: String(values.value.expires_at || '').trim() || null,
    })
    issued.value = created
    toastOk('API Key 已签发，请立即复制')
    emit('saved', created)
  } catch (err) {
    error.value = errorMessageOf(err)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AppDialog v-model:open="open" title="签发 API Key" width="620px">
    <template v-if="issued">
      <div class="note note--wait">
        密钥明文只在签发这一刻返回，关掉窗口后再也查不到。请现在复制并交给业务系统。
      </div>
      <div class="secret">
        <span class="code">{{ issued.api_key }}</span>
        <CopyButton :text="issued.api_key || ''" label="复制密钥" />
      </div>
    </template>

    <DynamicForm v-else ref="formRef" v-model="values" :fields="fields" :error="error" />

    <template #footer>
      <ElButton v-if="issued" type="primary" @click="open = false">我已复制，关闭</ElButton>
      <template v-else>
        <ElButton @click="open = false">取消</ElButton>
        <ElButton type="primary" :loading="submitting" @click="submit">签发</ElButton>
      </template>
    </template>
  </AppDialog>
</template>

<style scoped>
/* 明文密钥单独摆一行，长密钥换行也不撑破弹窗 */
.secret {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  padding: 10px 12px;
  border: 1px solid var(--rule);
  border-radius: var(--radius);
  background: var(--surface-sunken);
}
</style>
