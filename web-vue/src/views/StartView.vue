<script setup lang="ts">
import { ElButton, ElInput, ElOption, ElSelect } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'

import { safe } from '@/api/http'
import { actionApi } from '@/api/modules/action'
import { approvalApi } from '@/api/modules/approval'
import type { StartInstanceInput } from '@/api/modules/approval'
import { orgApi } from '@/api/modules/org'
import { processApi } from '@/api/modules/process'
import type {
  BusinessAction,
  Person,
  Process,
  StartedInstance,
  Tenant,
  TenantContext,
} from '@/api/types'
import CopyButton from '@/components/common/CopyButton.vue'
import CurlDialog from '@/components/dialogs/CurlDialog.vue'
import StartResultDialog from '@/components/dialogs/StartResultDialog.vue'
import DynamicForm from '@/components/form/DynamicForm.vue'
import EmptyState from '@/components/layout/EmptyState.vue'
import ErrorPanel from '@/components/layout/ErrorPanel.vue'
import PageHead from '@/components/layout/PageHead.vue'
import PanelCard from '@/components/layout/PanelCard.vue'
import { useAsyncPage } from '@/composables/useAsyncPage'
import { errorMessageOf } from '@/composables/useConfirm'
import { useUrlFilters } from '@/composables/useUrlFilters'
import { useConfigStore } from '@/stores/config'
import { useCredentialsStore } from '@/stores/credentials'
import { maskSecret } from '@/utils/format'
import { parseJsonInput, stringifyJson } from '@/utils/json'
import type { DynamicFieldSpec } from '@/utils/nodeConfigForm'
import { toastError, toastOk } from '@/utils/notify'
import { buildCurl } from '@/utils/payload'
import { sampleFormFromSchema } from '@/utils/schemaForm'

interface StartData {
  tenants: Tenant[]
  processes: Process[]
  persons: Person[]
  actions: BusinessAction[]
  /** 管理台自动借用该租户最近签发的有效密钥（契约⑧），联调时不用手工复制 */
  borrowedKey: string | null
}

const EMPTY: StartData = { tenants: [], processes: [], persons: [], actions: [], borrowedKey: null }

const config = useConfigStore()
const credentials = useCredentialsStore()
const tenantFilter = useUrlFilters().filter('tenant')

const { data, loading, error, refresh } = useAsyncPage<StartData>(async () => {
  // 租户一个都拉不到时这一页没有发起身份可用，这一项不兜底，交给整页错误面板（旧版同样如此）
  const tenants = await credentials.loadTenants()
  const [processes, persons, actions] = await Promise.all([
    safe(processApi.processes(200), []),
    safe(orgApi.persons(200), []),
    safe(actionApi.list(200), []),
  ])
  // 地址栏里的租户取不到时不写死：回落到第一个租户（旧版 find(...) || tenants[0] 同口径）
  const picked = tenants.find((item) => item.id === tenantFilter.value) || tenants[0] || null
  return {
    tenants,
    processes,
    persons,
    actions,
    borrowedKey: picked ? await credentials.tenantApiKey(picked.id) : null,
  }
}, EMPTY)

// 换租户要重新借用密钥、重算可选流程，所以整页重取；租户由下拉写回地址栏
watch(tenantFilter, () => void refresh())
onMounted(refresh)

const currentTenant = computed(() => {
  const list = data.value.tenants
  return list.find((item) => item.id === tenantFilter.value) || list[0] || null
})
const currentTenantId = computed(() => currentTenant.value?.id || '')
const selectedTenant = computed({
  get: () => currentTenantId.value,
  set: (tenantId: string) => {
    tenantFilter.value = tenantId
  },
})

// 只有启用且已发布版本的流程能发起（旧版 usable 同口径）
const usableProcesses = computed(() =>
  data.value.processes.filter((item) => item.status === 'ENABLED' && item.current_version_id),
)

const processOptions = computed(() =>
  usableProcesses.value.map((item) => ({
    value: item.id,
    label: `${item.name} · V${item.current_version_no}`,
  })),
)
const applicantOptions = computed(() => [
  { value: '', label: '不指定' },
  ...data.value.persons.map((item) => ({ value: item.id, label: item.name })),
])
const actionOptions = computed(() => [
  { value: '', label: '不触发业务执行' },
  ...data.value.actions
    .filter((item) => item.status === 'ENABLED')
    .map((item) => ({ value: item.action_code, label: `${item.name}（${item.action_code}）` })),
])

const values = ref<Record<string, unknown>>({})
const formRef = ref<InstanceType<typeof DynamicForm> | null>(null)
const formError = ref('')
const submitting = ref(false)
const resultOpen = ref(false)
const startedResult = ref<StartedInstance | null>(null)
const curlOpen = ref(false)
const curlCommand = ref('')

const fields = computed<DynamicFieldSpec[]>(() => [
  {
    name: 'process_id',
    label: '审批流 *',
    type: 'select',
    required: true,
    options: processOptions.value,
    hint: usableProcesses.value.length ? '' : '没有已发布且启用的审批流，先去创建并发布一条。',
  },
  {
    name: 'business_key',
    label: '业务单号 *',
    type: 'text',
    required: true,
    placeholder: 'PAY-20260923-001',
    hint: '同一租户、同一流程下重复使用同一个单号会命中幂等。',
  },
  {
    name: 'title',
    label: '审批单标题 *',
    type: 'text',
    required: true,
    placeholder: '供应商付款申请',
  },
  { name: 'applicant_person_id', label: '发起人', type: 'select', options: applicantOptions.value },
  {
    name: 'action_code',
    label: '业务动作',
    type: 'select',
    options: actionOptions.value,
    hint: '选择动作后，审批通过会回调业务系统。',
  },
  {
    name: 'approval_form',
    label: '审批表单 approval_form',
    type: 'code',
    wide: true,
    placeholder: '{ "amount": 10000 }',
    hint: '按流程版本的表单 Schema 校验，分支条件引用这里的字段。',
  },
  {
    name: 'execution_payload',
    label: '执行参数 execution_payload',
    type: 'code',
    wide: true,
    placeholder: '{ "payment_id": "PAY-20260923-001", "amount": 10000 }',
    hint: '按业务动作的请求参数 Schema 校验，只有审批通过后才会发给业务系统。',
  },
])

// 审批流下拉不给空选项：旧版 select 里第一个流程就是默认选中项。流程列表变了、
// 或选中的流程被停用/回退后，把失效的选择换成第一个
watch(
  usableProcesses,
  (list) => {
    const current = String(values.value.process_id || '')
    if (list.some((item) => item.id === current)) return
    values.value = { ...values.value, process_id: list[0]?.id || '' }
  },
  { immediate: true },
)

/**
 * 临时密钥优先于自动借用。
 * 旧版是反过来的（`借用 || 手填`），手填的密钥只在租户没有可用密钥时才生效 ——
 * 与输入框的提示语「留空则使用上面自动借用的密钥」和按钮提示「本次会话将使用这个密钥」
 * 自相矛盾，填了却不生效。这里按提示语的语义来。
 */
const manualKey = computed(() => config.apiKey)
const effectiveKey = computed(() => manualKey.value || data.value.borrowedKey || '')
const manualKeyDraft = ref(config.apiKey)

const context = ref<TenantContext | null>(null)
let contextGeneration = 0

/**
 * 借用的密钥可能已被撤销或过期，所以拿 /api/tenant/context 实打实验一次，
 * 顺带拿到「这个密钥属于哪个租户」（tenant_id 由密钥决定，不进请求体）。
 * 带序号是因为切租户时会连着触发几次，回来晚的结果不能盖掉新的。
 */
async function verifyKey(): Promise<void> {
  const current = ++contextGeneration
  const key = effectiveKey.value
  const result = key ? await safe(approvalApi.tenantContext(key), null) : null
  if (current === contextGeneration) context.value = result
}

watch(effectiveKey, () => void verifyKey(), { immediate: true })

/**
 * 「使用」按钮。
 * 空值表示弃用临时密钥、回到自动借用：旧版这里只弹一句「请先填入密钥」，
 * 而临时密钥是持久化的，界面上再没有第二个入口能撤掉它（配错了就卡死）。
 */
function useManualKey(): void {
  const value = manualKeyDraft.value.trim()
  if (!value) {
    config.setApiKey('')
    toastOk('已改回自动借用该租户的密钥')
    return
  }
  config.setApiKey(value)
  toastOk('本次会话将使用这个密钥')
}

/** 表单值 → 发起请求体。旧版「提交」与「生成调用示例」各拼了一遍，这里合成一处免得走样。 */
function payloadOf(): StartInstanceInput {
  const payload: StartInstanceInput = {
    business_key: String(values.value.business_key || '').trim(),
    title: String(values.value.title || '').trim(),
    applicant_person_id: String(values.value.applicant_person_id || '') || null,
    approval_form: parseJsonInput(values.value.approval_form, '审批表单') as Record<
      string,
      unknown
    >,
    execution_payload: parseJsonInput(values.value.execution_payload, '执行参数') as Record<
      string,
      unknown
    >,
  }
  const actionCode = String(values.value.action_code || '')
  if (actionCode) payload.action_code = actionCode
  return payload
}

function reportFailure(err: unknown): void {
  const message = errorMessageOf(err)
  formError.value = message
  toastError(message)
}

/** 按选中流程当前版本的表单 Schema 造一份模板，字段多的时候省得手敲 */
async function fillSampleForm(): Promise<void> {
  const process = usableProcesses.value.find(
    (item) => item.id === String(values.value.process_id || ''),
  )
  if (!process || !process.current_version_id) {
    toastError('该流程还没有发布版本，无法生成表单示例')
    return
  }
  try {
    const graph = await processApi.graph(process.current_version_id)
    const sample = sampleFormFromSchema(graph.form_schema)
    values.value = { ...values.value, approval_form: stringifyJson(sample) }
    if (!Object.keys(sample).length) toastOk('该版本没有声明表单字段，可以留空提交')
  } catch (err) {
    reportFailure(err)
  }
}

function openCurl(): void {
  const processId = String(values.value.process_id || '')
  if (!processId) {
    toastError('请先选择审批流')
    return
  }
  try {
    curlCommand.value = buildCurl(config.base, processId, payloadOf(), effectiveKey.value)
    curlOpen.value = true
  } catch (err) {
    reportFailure(err)
  }
}

async function submit(): Promise<void> {
  // 必填由 DynamicForm 自己判（空值口径与旧版 formDialog 一致），失败时在表单底部给文案
  if (!(await formRef.value?.validate())) return
  if (!effectiveKey.value) {
    toastError('该租户没有可用的 API Key，请先在租户页面签发一个')
    return
  }
  formError.value = ''
  let payload: StartInstanceInput
  try {
    payload = payloadOf()
  } catch (err) {
    reportFailure(err)
    return
  }
  submitting.value = true
  try {
    const started = await approvalApi.start(
      String(values.value.process_id || ''),
      payload,
      effectiveKey.value,
    )
    // 这次发起会挂到该租户名下，借来的密钥与使用记录缓存立刻失效
    credentials.invalidate()
    toastOk(started.idempotent_replay ? '命中幂等，返回已有审批实例' : '审批已发起')
    startedResult.value = started
    resultOpen.value = true
  } catch (err) {
    reportFailure(err)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <PageHead
    title="发起审批"
    note="这一页模拟业务系统调用发起接口。真实接入时由业务系统用租户 API Key 调用，tenant_id 不进入请求体，由密钥决定。"
  />

  <ErrorPanel v-if="error" :error="error" />

  <PanelCard v-else-if="loading && !data.tenants.length">
    <div class="loading">正在读取数据…</div>
  </PanelCard>

  <PanelCard v-else-if="!data.tenants.length">
    <EmptyState
      title="还没有租户"
      hint="发起审批需要以某个租户的身份调用，先创建租户并签发 API Key。"
    >
      <a class="btn btn--sm" href="#/tenants">去创建租户</a>
    </EmptyState>
  </PanelCard>

  <template v-else>
    <PanelCard title="第一步 · 选择发起身份">
      <template #actions>
        <span v-if="context" class="panel__note">
          密钥已验证：{{ context.tenant_name }}（{{ context.tenant_code }}）
        </span>
      </template>

      <div class="form__row--split">
        <div class="field">
          <label class="field__label">租户</label>
          <ElSelect v-model="selectedTenant" style="width: 100%">
            <ElOption
              v-for="tenant in data.tenants"
              :key="tenant.id"
              :value="tenant.id"
              :label="`${tenant.name}（${tenant.code}）`"
            />
          </ElSelect>
          <div class="field__hint">
            管理台自动借用该租户最近签发的有效 API Key，不需要手工复制。
          </div>
        </div>

        <div class="field">
          <label class="field__label">当前使用的密钥</label>
          <template v-if="effectiveKey">
            <div class="key-line">
              <span class="code">{{ maskSecret(effectiveKey) }}</span>
              <CopyButton :text="effectiveKey" label="复制完整密钥" />
            </div>
            <div class="field__hint">
              {{
                manualKey ? '正在使用下面填写的临时密钥' : '管理台自动借用该租户最近签发的有效密钥'
              }}
            </div>
          </template>
          <div v-else class="note note--wait">
            该租户没有可用的 API Key，<a :href="`#/tenants/${currentTenantId}`">去签发一个</a
            >，或临时使用下面的密钥。
          </div>
        </div>
      </div>

      <div class="manual-key">
        <label class="field__label">临时使用其他密钥（可选）</label>
        <div class="manual-key__row">
          <ElInput v-model="manualKeyDraft" placeholder="留空并点「使用」则回到自动借用的密钥" />
          <ElButton @click="useManualKey">使用</ElButton>
        </div>
      </div>
    </PanelCard>

    <PanelCard title="第二步 · 填写审批内容">
      <template #actions>
        <!-- 旧版把「按 Schema 生成示例」挂在 approval_form 的标签上。DynamicForm 是共享组件、
             不开放自定义插槽（也不能为这一页动它），所以两个按钮一起放在面板头 -->
        <ElButton size="small" @click="fillSampleForm">按 Schema 生成示例</ElButton>
        <ElButton size="small" @click="openCurl">生成调用示例</ElButton>
      </template>

      <DynamicForm ref="formRef" v-model="values" :fields="fields" :error="formError" />

      <div class="submit-row">
        <ElButton type="primary" :loading="submitting" @click="submit">发起审批</ElButton>
      </div>
    </PanelCard>
  </template>

  <StartResultDialog v-model:open="resultOpen" :started="startedResult" :persons="data.persons" />
  <CurlDialog v-model:open="curlOpen" :command="curlCommand" />
</template>

<style scoped>
/* 密钥一行：掩码 + 复制按钮 */
.key-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* 临时密钥输入框：旧版限宽 620px 并跟上面那行留出间距 */
.manual-key {
  max-width: 620px;
  margin-top: 14px;
}
.manual-key__row {
  display: flex;
  gap: 8px;
  margin-top: 5px;
}

.submit-row {
  display: flex;
  gap: 8px;
  margin-top: 14px;
}
</style>
