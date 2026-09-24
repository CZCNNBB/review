<script setup lang="ts">
import { ElOption, ElSelect } from 'element-plus'
import { ref, watch } from 'vue'

import type { JSONSchema } from '@/types/domain'
import {
  applyFormFields,
  DATE_FORMATS,
  FORM_FIELD_TYPES,
  formFieldsFromSchema,
  uniqueFieldKey,
  type FormFieldRow,
  type FormFieldType,
} from '@/utils/schemaForm'

/**
 * 审批表单字段表：Schema 与「字段列表」的互转。
 *
 * 行内编辑**故意不重绘整个表格** —— 旧版就是靠"改一行不重渲染"保住输入焦点的，
 * 每次敲一个字符都重建 DOM 的话光标会跳。只有类型变更与增删/移动才需要重排。
 */
const props = defineProps<{
  schema: JSONSchema
  readonly?: boolean
}>()

const emit = defineEmits<{ (event: 'update:schema', schema: JSONSchema): void }>()

const rows = ref<FormFieldRow[]>([])

watch(
  () => props.schema,
  (schema) => {
    rows.value = formFieldsFromSchema(schema).fields
  },
  { immediate: true, deep: true },
)

function commit(): void {
  emit('update:schema', applyFormFields(props.schema, rows.value))
}

/** 单元格编辑：改本地行 + 回写 Schema，但不重建行，焦点不丢。 */
function editCell(index: number, prop: 'key' | 'title' | 'options', value: string): void {
  rows.value[index][prop] = value
  commit()
}

function toggleRequired(index: number, value: boolean): void {
  rows.value[index].required = value
  commit()
}

/** 换类型要连控件一起换（选项 ↔ 日期格式），所以整体重排。 */
function changeType(index: number, type: FormFieldType): void {
  rows.value[index].type = type
  if (type === 'enum' || type === 'multiselect') rows.value[index].options = ''
  if (type === 'date') rows.value[index].options = DATE_FORMATS[0]
  commit()
  rows.value = [...rows.value]
}

function addField(): void {
  rows.value = [
    ...rows.value,
    {
      key: uniqueFieldKey(rows.value),
      title: '',
      required: false,
      type: 'string',
      options: '',
    },
  ]
  commit()
}

function dropField(index: number): void {
  rows.value = rows.value.filter((_, position) => position !== index)
  commit()
}

function moveField(index: number, step: number): void {
  const target = index + step
  if (target < 0 || target >= rows.value.length) return
  const next = [...rows.value]
  const [moved] = next.splice(index, 1)
  next.splice(target, 0, moved)
  rows.value = next
  commit()
}

function optionsPlaceholder(type: FormFieldType): string {
  return type === 'enum' || type === 'multiselect' ? '用、分隔，例如：差旅、办公' : '—'
}
</script>

<template>
  <div v-if="!rows.length" class="empty">
    <div class="empty__title">还没有表单字段</div>
    <div>没有字段时，发起审批不需要填写任何表单数据，条件分支也就无从选起。</div>
  </div>

  <div v-else class="tbl-wrap">
    <table class="tbl field-tbl">
    <thead>
      <tr>
        <th style="width: 150px">字段键</th>
        <th style="width: 150px">显示名</th>
        <th style="width: 110px">类型</th>
        <th style="width: 60px">必填</th>
        <th>选项 · 格式</th>
        <th style="width: 130px" class="tbl__actions">操作</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="(row, index) in rows" :key="`${row.key}-${index}`">
        <td>
          <input
            class="input input--cell"
            :value="row.key"
            :readonly="props.readonly"
            @change="editCell(index, 'key', ($event.target as HTMLInputElement).value.trim())"
          />
        </td>
        <td>
          <input
            class="input input--cell"
            :value="row.title"
            :readonly="props.readonly"
            placeholder="默认同字段键"
            @change="editCell(index, 'title', ($event.target as HTMLInputElement).value.trim())"
          />
        </td>
        <td>
          <ElSelect
            :model-value="row.type"
            :disabled="props.readonly || row.type === 'unsupported'"
            size="small"
            style="width: 100%"
            @update:model-value="changeType(index, $event as FormFieldType)"
          >
            <ElOption
              v-for="option in FORM_FIELD_TYPES"
              :key="option.value"
              :value="option.value"
              :label="option.label"
            />
            <ElOption v-if="row.type === 'unsupported'" value="unsupported" label="复杂结构" />
          </ElSelect>
        </td>
        <td class="field-tbl__check">
          <input
            type="checkbox"
            :checked="row.required"
            :disabled="props.readonly"
            @change="toggleRequired(index, ($event.target as HTMLInputElement).checked)"
          />
        </td>
        <td>
          <ElSelect
            v-if="row.type === 'date'"
            :model-value="row.options || 'date'"
            :disabled="props.readonly"
            size="small"
            style="width: 100%"
            @update:model-value="editCell(index, 'options', String($event))"
          >
            <ElOption value="date" label="日期（2026-09-30）" />
            <ElOption value="date-time" label="日期时间" />
            <ElOption value="time" label="时间" />
          </ElSelect>
          <input
            v-else
            class="input input--cell"
            :value="row.options"
            :readonly="props.readonly || row.type === 'unsupported'"
            :disabled="row.type === 'unsupported'"
            :placeholder="optionsPlaceholder(row.type)"
            @change="editCell(index, 'options', ($event.target as HTMLInputElement).value)"
          />
        </td>
        <td class="tbl__actions">
          <template v-if="!props.readonly">
            <button class="btn--link btn--sm" type="button" @click="moveField(index, -1)">
              上移
            </button>
            <button class="btn--link btn--sm" type="button" @click="moveField(index, 1)">
              下移
            </button>
            <button class="btn--link btn--sm is-danger" type="button" @click="dropField(index)">
              删除
            </button>
          </template>
        </td>
      </tr>
    </tbody>
    </table>
  </div>

  <div
    v-if="!props.readonly"
    class="panel__body"
    style="border-top: 1px solid var(--rule-weak); padding: 12px 16px"
  >
    <button class="btn btn--sm btn--primary" type="button" @click="addField">新增字段</button>
  </div>
</template>
