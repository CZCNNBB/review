import type { JSONSchema, UISchema } from '@/types/domain'

import { DATE_FORMATS, splitOptions } from './schemaForm'

/** 节点定义的配置项类型。比表单多一个人员选择器，少一个多选。 */
export type ConfigFieldType =
  | 'string'
  | 'textarea'
  | 'number'
  | 'integer'
  | 'boolean'
  | 'enum'
  | 'person-select'
  | 'date'
  | 'unsupported'

export interface ConfigFieldRow {
  key: string
  title: string
  required: boolean
  type: ConfigFieldType
  options: string
}

export const CONFIG_FIELD_TYPES: ReadonlyArray<{ value: ConfigFieldType; label: string }> = [
  { value: 'string', label: '文本' },
  { value: 'textarea', label: '多行文本' },
  { value: 'number', label: '数字' },
  { value: 'integer', label: '整数' },
  { value: 'boolean', label: '是 / 否' },
  { value: 'enum', label: '下拉选择' },
  { value: 'person-select', label: '人员选择器' },
  { value: 'date', label: '日期' },
]

export function configFieldTypeLabel(type: ConfigFieldType): string {
  return CONFIG_FIELD_TYPES.find((item) => item.value === type)?.label || type
}

/** ui_schema 里某一项如果是对象就取出来，其他形状（数组、字符串）一律当空。 */
function uiWidgetHolder(value: unknown): Record<string, unknown> {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  return {}
}

function uiWidgetOf(value: unknown): unknown {
  return uiWidgetHolder(value)['ui:widget']
}

/** 审批人数组的元素结构：`{ person_id }`。人员选择器认这个形状。 */
export function isPersonItemSchema(items?: JSONSchema | null): boolean {
  return Boolean(items && items.type === 'object' && items.properties && items.properties.person_id)
}

/**
 * 节点定义的 config_schema_json + ui_schema_json → 配置项表。
 * 两者合起来才是"这张表"，用户不需要分别理解两份 JSON。
 */
export function configFieldsFromSchema(
  schema?: JSONSchema | null,
  uiSchema?: UISchema | null,
): { fields: ConfigFieldRow[]; simple: boolean } {
  const properties = schema?.properties || {}
  const ui = uiSchema || {}
  const required = new Set(schema?.required || [])
  const fields: ConfigFieldRow[] = []

  for (const [key, rule] of Object.entries(properties)) {
    const widget = uiWidgetOf(ui[key])
    const field: ConfigFieldRow = {
      key,
      title: rule.title || key,
      required: required.has(key),
      type: 'string',
      options: '',
    }

    if (widget === 'person-select' || isPersonItemSchema(rule.items)) {
      field.type = 'person-select'
    } else if (widget === 'textarea') {
      field.type = 'textarea'
    } else if (rule.type === 'string' && Array.isArray(rule.enum)) {
      field.type = 'enum'
      field.options = rule.enum.join('、')
    } else if (rule.type === 'string' && DATE_FORMATS.includes(rule.format as never)) {
      field.type = 'date'
      field.options = String(rule.format)
    } else if (['string', 'number', 'integer', 'boolean'].includes(String(rule.type))) {
      field.type = rule.type as ConfigFieldType
    } else {
      field.type = 'unsupported'
    }

    fields.push(field)
  }

  return { fields, simple: fields.every((field) => field.type !== 'unsupported') }
}

/** 配置项表 → config_schema_json + ui_schema_json（同样保留表格管不到的约束）。 */
export function applyConfigFields(
  schema: JSONSchema | null | undefined,
  uiSchema: UISchema | null | undefined,
  fields: ConfigFieldRow[],
): { schema: JSONSchema; uiSchema: UISchema } {
  const originals = schema?.properties || {}
  const originalUi = uiSchema || {}
  const properties: Record<string, JSONSchema> = {}
  const ui: UISchema = { ...originalUi } // 保留 ui:order 这类根级规则
  const required: string[] = []

  fields.forEach((field) => {
    if (!field.key) return

    const rule: JSONSchema = { ...(originals[field.key] || {}) }
    const uiRule: Record<string, unknown> = { ...uiWidgetHolder(originalUi[field.key]) }

    if (field.type === 'unsupported') {
      properties[field.key] = rule
      return
    }

    delete rule.enum
    delete rule.format
    delete rule.items
    delete uiRule['ui:widget']

    if (field.type === 'enum') {
      rule.type = 'string'
      rule.enum = splitOptions(field.options)
      uiRule['ui:widget'] = 'select'
    } else if (field.type === 'person-select') {
      rule.type = 'array'
      rule.minItems = rule.minItems || 1
      rule.items = {
        type: 'object',
        additionalProperties: false,
        required: ['person_id'],
        properties: { person_id: { type: 'string', format: 'uuid', title: '人员 ID' } },
      }
      uiRule['ui:widget'] = 'person-select'
    } else if (field.type === 'textarea') {
      rule.type = 'string'
      uiRule['ui:widget'] = 'textarea'
    } else if (field.type === 'date') {
      rule.type = 'string'
      rule.format =
        field.options && DATE_FORMATS.includes(field.options as never) ? field.options : 'date'
    } else {
      rule.type = field.type
    }

    rule.title = field.title || field.key
    properties[field.key] = rule

    if (Object.keys(uiRule).length) ui[field.key] = uiRule
    else delete ui[field.key]

    if (field.required) required.push(field.key)
  })

  // 已经删掉的配置项不要留下孤立的 ui 配置
  Object.keys(ui).forEach((key) => {
    if (!key.startsWith('ui:') && !properties[key]) delete ui[key]
  })

  const next: JSONSchema = { ...(schema || {}) }
  next.type = 'object'
  next.properties = properties
  if (required.length) next.required = required
  else delete next.required

  return { schema: next, uiSchema: ui }
}
