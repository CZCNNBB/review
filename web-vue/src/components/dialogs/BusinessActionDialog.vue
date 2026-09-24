<script setup lang="ts">
import { ElButton } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { actionApi } from '@/api/modules/action'
import type { BusinessActionInput } from '@/api/modules/action'
import type { BusinessAction } from '@/api/types'
import AppDialog from '@/components/common/AppDialog.vue'
import DynamicForm from '@/components/form/DynamicForm.vue'
import { errorMessageOf } from '@/composables/useConfirm'
import type { JSONSchema } from '@/types/domain'
import { parseJsonInput, stringifyJson } from '@/utils/json'
import type { DynamicFieldSpec } from '@/utils/nodeConfigForm'
import { toastOk } from '@/utils/notify'

// 新建 / 编辑业务动作。旧版按 isNew 拼两套字段，差异只有动作标识必填与末尾的状态，
// 这里合成一个弹窗：动作标识只在新建时可填，编辑时提交也不带它（后端不接受改标识）。
const open = defineModel<boolean>('open', { default: false })

const props = defineProps<{
  /** 传了就是编辑，不传就是新建 */
  action?: BusinessAction | null
}>()

const emit = defineEmits<{ (event: 'saved', action: BusinessAction): void }>()

const isNew = computed(() => !props.action)
const values = ref<Record<string, unknown>>({})
const error = ref('')
const submitting = ref(false)
const formRef = ref<InstanceType<typeof DynamicForm> | null>(null)

const fields = computed<DynamicFieldSpec[]>(() => [
  {
    name: 'action_code',
    label: isNew.value ? '动作标识 *' : '动作标识',
    type: 'text',
    required: isNew.value,
    placeholder: 'PAYMENT_EXECUTE',
    hint: isNew.value
      ? '全局唯一，统一转大写，创建后不可修改'
      : '动作标识创建后不可修改，这里仅作展示',
  },
  { name: 'name', label: '动作名称 *', type: 'text', required: true, placeholder: '执行付款' },
  {
    name: 'http_method',
    label: '调用方法',
    type: 'select',
    options: [
      { value: 'POST', label: 'POST' },
      { value: 'PUT', label: 'PUT' },
      { value: 'PATCH', label: 'PATCH' },
    ],
  },
  {
    name: 'relative_path',
    label: '相对路径 *',
    type: 'text',
    required: true,
    placeholder: '/payments/execute',
    hint: '必须以单个 / 开头；实际地址由租户的回调基础地址拼接得到',
  },
  { name: 'timeout_ms', label: '超时时间（毫秒）', type: 'number', placeholder: '5000' },
  {
    name: 'success_status_codes',
    label: '成功状态码',
    type: 'text',
    placeholder: '200,201',
    hint: '逗号分隔；留空表示全部 2xx 视为成功',
  },
  {
    name: 'request_schema_json',
    label: '执行参数 Schema',
    type: 'code',
    wide: true,
    hint: '校验发起审批时传入的 execution_payload，根类型必须是 object',
    placeholder:
      '{\n  "type": "object",\n  "required": ["payment_id"],\n  "properties": { "payment_id": { "type": "string" } }\n}',
  },
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
          hint: '停用后不能用于新申请，已经运行的实例不受影响',
        },
      ]),
])

watch(
  () => [open.value, props.action] as const,
  ([isOpen]) => {
    if (!isOpen) return
    error.value = ''
    values.value = props.action
      ? {
          action_code: props.action.action_code,
          name: props.action.name,
          http_method: props.action.http_method,
          relative_path: props.action.relative_path,
          timeout_ms: props.action.timeout_ms,
          success_status_codes: (props.action.success_status_codes || []).join(','),
          // 表单里放的是 JSON 文本，Schema 为空时给空串而不是 "{}"
          request_schema_json: Object.keys(props.action.request_schema || {}).length
            ? stringifyJson(props.action.request_schema)
            : '',
          status: props.action.status,
        }
      : {
          action_code: '',
          name: '',
          http_method: 'POST',
          relative_path: '',
          timeout_ms: 5000,
          success_status_codes: '',
          request_schema_json: '',
        }
  },
  { immediate: true },
)

/**
 * 表单值 → 接口载荷（对应旧版 payloadOf）。
 * 成功状态码在这里切成数字数组；Schema 是文本，解析失败要抛出去让用户看到是哪一项不对。
 * 数字控件清空时给的是空串，按旧版语义回落成默认的 5000。
 *
 * 与旧版的差别只有一处：不再提交 description。旧版弹窗里根本没有这个字段，
 * 却每次都带上 `description: values.description || null`，编辑会把接口里配好的说明抹掉。
 * 这里干脆不带，后端不动这个字段。
 */
function payloadOf(): BusinessActionInput {
  const codes = String(values.value.success_status_codes || '').trim()
  const timeout = values.value.timeout_ms
  const payload: BusinessActionInput = {
    name: String(values.value.name || '').trim(),
    http_method: String(values.value.http_method || '') || 'POST',
    relative_path: String(values.value.relative_path || '').trim(),
    timeout_ms:
      timeout === '' || timeout === null || timeout === undefined ? 5000 : Number(timeout),
    request_schema_json: parseJsonInput(
      values.value.request_schema_json,
      '执行参数 Schema',
    ) as JSONSchema,
  }
  if (codes) {
    payload.success_status_codes = codes
      .split(',')
      .map((item) => Number(item.trim()))
      .filter((item) => !Number.isNaN(item))
  }
  if (props.action) payload.status = String(values.value.status)
  else payload.action_code = String(values.value.action_code).trim()
  return payload
}

async function submit(): Promise<void> {
  if (!(await formRef.value?.validate())) return
  submitting.value = true
  error.value = ''
  try {
    const saved = props.action
      ? await actionApi.update(props.action.id, payloadOf())
      : await actionApi.create(payloadOf())
    toastOk(props.action ? '业务动作已更新' : '业务动作已创建')
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
  <AppDialog v-model:open="open" :title="isNew ? '新建业务动作' : '编辑业务动作'" width="820px">
    <DynamicForm ref="formRef" v-model="values" :fields="fields" :error="error" />
    <template #footer>
      <ElButton @click="open = false">取消</ElButton>
      <ElButton type="primary" :loading="submitting" @click="submit">
        {{ isNew ? '创建动作' : '保存' }}
      </ElButton>
    </template>
  </AppDialog>
</template>
