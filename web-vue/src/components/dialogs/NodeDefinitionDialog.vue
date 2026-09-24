<script lang="ts">
/** 执行类型文案。后端只注册了开始、人工审批、结束三个执行器，节点定义造不出新类型。 */
const NODE_TYPE_TEXT: Record<string, string> = {
  START: '开始',
  APPROVAL: '人工审批',
  END: '结束',
}

/** 列表页也要显示这层文案，从这里导出，避免两处各写一份。 */
export function nodeTypeLabel(nodeType: string): string {
  return NODE_TYPE_TEXT[nodeType] || nodeType
}

/** 高级模式的 Schema 示例：schema 为空时当占位提示用，内容与旧版一致。 */
const CONFIG_SCHEMA_SAMPLE = `{
  "type": "object",
  "title": "人工审批",
  "required": ["approval_mode", "approvers"],
  "properties": {
    "approval_mode": {
      "type": "string",
      "title": "审批模式",
      "enum": ["AND", "OR"]
    },
    "approvers": {
      "type": "array",
      "title": "审批人",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["person_id"],
        "properties": {
          "person_id": { "type": "string", "format": "uuid", "title": "人员 ID" }
        }
      }
    }
  }
}`
</script>

<script setup lang="ts">
import { ElButton, ElCheckbox, ElInput, ElOption, ElSelect } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { processApi } from '@/api/modules/process'
import type { NodeDefinitionInput } from '@/api/modules/process'
import AppDialog from '@/components/common/AppDialog.vue'
import CodeTextarea from '@/components/common/CodeTextarea.vue'
import DynamicForm from '@/components/form/DynamicForm.vue'
import EmptyState from '@/components/layout/EmptyState.vue'
import { errorMessageOf } from '@/composables/useConfirm'
import type { JSONSchema, NodeDefinition, UISchema } from '@/types/domain'
import type { DynamicFieldSpec } from '@/utils/nodeConfigForm'
import { parseJsonInput, stringifyJson } from '@/utils/json'
import { toastOk } from '@/utils/notify'
import {
  applyConfigFields,
  configFieldsFromSchema,
  CONFIG_FIELD_TYPES,
  type ConfigFieldRow,
} from '@/utils/schemaConfig'
import { uniqueFieldKey } from '@/utils/schemaForm'

/**
 * 节点定义的新建 / 编辑。
 *
 * 元信息走表单；「允许配置哪些项」有两套编辑方式：
 * - 字段表：本地数组 + v-model，行内编辑不重渲染（旧版靠不重渲染保住输入焦点）；
 * - 高级模式：直接改 JSON Schema 与配置面板规则，切回字段表前先试解析，
 *   含量表表达不了的结构就拒绝切换，避免把配置丢掉。
 * 两者的换算复用 utils/schemaConfig 的纯函数，与旧版是同一份规则。
 */
const open = defineModel<boolean>('open', { default: false })

const props = defineProps<{
  /** 传了就是编辑，不传就是新建 */
  definition?: NodeDefinition | null
}>()

const emit = defineEmits<{ (event: 'saved'): void }>()

const isNew = computed(() => !props.definition)

const values = ref<Record<string, unknown>>({})
const error = ref('')
const submitting = ref(false)
const formRef = ref<InstanceType<typeof DynamicForm> | null>(null)

const advanced = ref(false)
const schemaText = ref('')
const uiText = ref('')
const fields = ref<ConfigFieldRow[]>([])
// 字段表换算 JSON 的基准：进弹窗时来自定义，从高级模式切回来时更新为解析结果。
// 等价于旧版的 draft.schema —— 每次改动都以它为基准重算，不会反复叠加。
const baseSchema = ref<JSONSchema | null>(null)
const baseUi = ref<UISchema | null>(null)

const metaFields = computed<DynamicFieldSpec[]>(() => [
  ...(isNew.value
    ? [
        {
          name: 'node_type',
          label: '执行类型 *',
          type: 'select' as const,
          required: true,
          options: Object.keys(NODE_TYPE_TEXT).map((value) => ({
            value,
            label: `${NODE_TYPE_TEXT[value]}（${value}）`,
          })),
          hint: '决定后端用哪个执行器，创建后不可修改',
        },
      ]
    : []),
  {
    name: 'name',
    label: '名称 *',
    type: 'text',
    required: true,
    placeholder: '财务审批',
    hint: '节点面板上显示的名字，全局唯一',
  },
  {
    name: 'description',
    label: '说明',
    type: 'text',
    placeholder: '金额超过 1 万元时需要财务审批',
  },
  { name: 'icon', label: '图标标识', type: 'text', placeholder: 'user-check' },
  {
    name: 'status',
    label: '状态',
    type: 'select',
    options: [
      { value: 'ENABLED', label: '启用' },
      { value: 'DISABLED', label: '停用' },
    ],
    hint: '停用后不能再放新节点，已有流程不受影响',
  },
])

watch(
  () => [open.value, props.definition] as const,
  ([isOpen]) => {
    if (!isOpen) return
    const definition = props.definition
    const parsed = configFieldsFromSchema(
      definition?.config_schema_json,
      definition?.ui_schema_json,
    )
    baseSchema.value = definition?.config_schema_json || {}
    baseUi.value = definition?.ui_schema_json || {}
    fields.value = parsed.fields
    // 字段表表达不了的结构只能留在高级模式里，否则用户一切换就丢配置
    advanced.value = !parsed.simple
    schemaText.value = stringifyJson(baseSchema.value)
    uiText.value = stringifyJson(baseUi.value)
    error.value = ''
    values.value = {
      // 旧版执行类型下拉默认落在第一项，这里保持同样的默认值
      node_type: definition?.node_type || 'START',
      name: definition?.name || '',
      description: definition?.description || '',
      icon: definition?.icon || '',
      status: definition?.status || 'ENABLED',
    }
  },
  { immediate: true },
)

/** 配置项字段表 → 两份 JSON。旧版每改一格就同步一次，这里改成用到时再算，结果一样。 */
function fieldsToJson(): { schema: JSONSchema; uiSchema: UISchema } {
  return applyConfigFields(baseSchema.value, baseUi.value, fields.value)
}

function toggleAdvanced(): void {
  error.value = ''
  if (advanced.value) {
    // 切回字段表前先试解析，含字段表表达不了的结构就不让切，避免丢配置
    const schemaInput = schemaText.value.trim()
    if (!schemaInput) {
      error.value = '配置 Schema 不能为空：没有配置项时请填 {}'
      return
    }
    try {
      const schema = parseJsonInput(schemaInput, '配置 Schema') as JSONSchema
      const uiSchema = parseJsonInput(uiText.value, '配置面板规则') as UISchema
      const next = configFieldsFromSchema(schema, uiSchema)
      if (!next.simple) throw new Error('这份 Schema 含字段表表达不了的结构，不能切回字段模式')
      baseSchema.value = schema
      baseUi.value = uiSchema
      fields.value = next.fields
    } catch (err) {
      error.value = errorMessageOf(err)
      return
    }
  } else {
    const applied = fieldsToJson()
    schemaText.value = stringifyJson(applied.schema)
    uiText.value = stringifyJson(applied.uiSchema)
  }
  advanced.value = !advanced.value
}

function addField(): void {
  fields.value.push({
    key: uniqueFieldKey(fields.value),
    title: '新配置项',
    type: 'string',
    required: false,
    options: '',
  })
}

function dropField(index: number): void {
  fields.value.splice(index, 1)
}

/** 上移 / 下移一格。越界不动，避免把行丢出去。 */
function moveField(index: number, offset: number): void {
  const target = index + offset
  if (target < 0 || target >= fields.value.length) return
  const moved = fields.value.splice(index, 1)[0]
  fields.value.splice(target, 0, moved)
}

// ElCheckbox 的更新值是 string | number | boolean，落到行上统一收成布尔
function setRequired(field: ConfigFieldRow, value: unknown): void {
  field.required = Boolean(value)
}

async function submit(): Promise<void> {
  if (!(await formRef.value?.validate())) return
  const name = String(values.value.name || '').trim()
  if (!name) {
    error.value = '名称不能为空'
    return
  }
  error.value = ''

  let schema: JSONSchema
  let uiSchema: UISchema
  if (advanced.value) {
    // 根类型是 object 的要求由后端把关，这里与旧版一样原样提交
    try {
      schema = parseJsonInput(schemaText.value, '配置 Schema') as JSONSchema
      uiSchema = parseJsonInput(uiText.value, '配置面板规则') as UISchema
    } catch (err) {
      error.value = errorMessageOf(err)
      return
    }
  } else {
    const applied = fieldsToJson()
    schema = applied.schema
    uiSchema = applied.uiSchema
  }

  const payload: NodeDefinitionInput = {
    name,
    description: String(values.value.description || '').trim() || null,
    icon: String(values.value.icon || '').trim() || null,
    status: String(values.value.status || 'ENABLED'),
    config_schema_json: schema,
    ui_schema_json: uiSchema,
  }

  submitting.value = true
  try {
    if (props.definition) {
      await processApi.updateNodeDefinition(props.definition.id, payload)
      toastOk('节点定义已更新')
    } else {
      await processApi.createNodeDefinition({
        ...payload,
        node_type: String(values.value.node_type || 'START'),
      })
      toastOk('节点定义已创建，回到编排页就能拖它')
    }
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
    :title="isNew ? '新建节点定义' : `编辑节点定义 · ${props.definition?.name}`"
    width="880px"
  >
    <DynamicForm ref="formRef" v-model="values" :fields="metaFields" />

    <div class="cfg-head">
      <h4 class="cfg-title">这个节点允许配置哪些项</h4>
      <ElButton size="small" @click="toggleAdvanced">
        {{ advanced ? '切到字段模式' : '高级模式（JSON）' }}
      </ElButton>
    </div>

    <template v-if="advanced">
      <div class="note">
        高级模式：直接编辑 JSON Schema 和配置面板规则，两者的根类型都必须是 object。
      </div>
      <div class="field cfg-field">
        <label class="field__label">配置 Schema</label>
        <CodeTextarea v-model="schemaText" :rows="10" :placeholder="CONFIG_SCHEMA_SAMPLE" />
      </div>
      <div class="field cfg-field">
        <label class="field__label">配置面板规则</label>
        <CodeTextarea v-model="uiText" :rows="8" />
        <div class="field__hint">例如 {"approvers": {"ui:widget": "person-select"}}</div>
      </div>
    </template>

    <template v-else>
      <div class="note">
        这里定义画布上放了这个节点之后，右侧弹窗里能配置哪些项。“人员选择器”就是让人从人员列表里挑人，不用手写
        ID。
      </div>
      <div v-if="fields.length" class="tbl-wrap cfg-table">
        <table class="tbl field-tbl">
          <thead>
            <tr>
              <th>配置键</th>
              <th>显示名</th>
              <th>类型</th>
              <th>必填</th>
              <th>下拉选项</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(field, index) in fields" :key="index">
              <td>
                <ElInput v-model="field.key" size="small" />
              </td>
              <td>
                <ElInput v-model="field.title" size="small" placeholder="显示给配置人看" />
              </td>
              <td>
                <ElSelect v-model="field.type" size="small" class="cfg-select">
                  <ElOption
                    v-for="type in CONFIG_FIELD_TYPES"
                    :key="type.value"
                    :value="type.value"
                    :label="type.label"
                  />
                </ElSelect>
              </td>
              <td class="cfg-required">
                <ElCheckbox
                  :model-value="field.required"
                  @update:model-value="setRequired(field, $event)"
                />
              </td>
              <td>
                <ElInput
                  v-if="field.type === 'enum'"
                  v-model="field.options"
                  size="small"
                  placeholder="用、分隔，例如 AND、OR"
                />
                <span v-else class="muted">—</span>
              </td>
              <td class="is-actions">
                <button class="btn--link btn--sm" type="button" @click="moveField(index, -1)">
                  上移
                </button>
                <button class="btn--link btn--sm" type="button" @click="moveField(index, 1)">
                  下移
                </button>
                <button class="btn--link btn--sm is-danger" type="button" @click="dropField(index)">
                  删除
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <EmptyState
        v-else
        title="这个节点没有可配置项"
        hint="例如“开始”和“结束”节点就不需要额外配置。"
      />
      <div class="cfg-add">
        <ElButton size="small" type="primary" @click="addField">新增配置项</ElButton>
      </div>
    </template>

    <div v-if="error" class="note note--wait cfg-error">{{ error }}</div>

    <template #footer>
      <ElButton @click="open = false">取消</ElButton>
      <ElButton type="primary" :loading="submitting" @click="submit">
        {{ isNew ? '创建定义' : '保存' }}
      </ElButton>
    </template>
  </AppDialog>
</template>

<style scoped>
.cfg-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 18px 0 8px;
}
.cfg-title {
  font-size: 14px;
}
.cfg-table {
  margin-top: 12px;
}
/* 类型下拉撑满单元格，和旁边的输入框对齐 */
.cfg-select {
  width: 100%;
}
.cfg-required {
  text-align: center;
}
.muted {
  color: var(--ink-3);
}
.cfg-add,
.cfg-field {
  margin-top: 12px;
}
.cfg-error {
  margin-top: 12px;
}
</style>
