import type { JSONSchema } from '@/types/domain'

/** 审批表单字段表里可选的数据类型。 */
export type FormFieldType =
  'string' | 'number' | 'integer' | 'boolean' | 'date' | 'enum' | 'multiselect' | 'unsupported'

/** 字段表的一行。options 对枚举/多选是选项文本，对日期是格式。 */
export interface FormFieldRow {
  key: string
  title: string
  required: boolean
  type: FormFieldType
  options: string
}

export const FORM_FIELD_TYPES: ReadonlyArray<{ value: FormFieldType; label: string }> = [
  { value: 'string', label: '文本' },
  { value: 'number', label: '数字' },
  { value: 'integer', label: '整数' },
  { value: 'boolean', label: '是 / 否' },
  { value: 'date', label: '日期' },
  { value: 'enum', label: '单选' },
  { value: 'multiselect', label: '多选' },
]

export const DATE_FORMATS = ['date', 'date-time', 'time'] as const

export function formFieldTypeLabel(type: FormFieldType): string {
  return FORM_FIELD_TYPES.find((item) => item.value === type)?.label || type
}

/**
 * JSON Schema → 字段表。
 * 表格表达不了的结构（嵌套对象、对象数组）标成 unsupported，并让调用方切成高级 JSON 模式，
 * 而不是假装它能用表格编辑。
 */
export function formFieldsFromSchema(schema?: JSONSchema | null): {
  fields: FormFieldRow[]
  simple: boolean
} {
  const properties = schema?.properties || {}
  const required = new Set(schema?.required || [])
  const fields: FormFieldRow[] = []

  for (const [key, rule] of Object.entries(properties)) {
    const field: FormFieldRow = {
      key,
      title: rule.title || key,
      required: required.has(key),
      type: 'string',
      options: '',
    }

    if (rule.type === 'string' && Array.isArray(rule.enum)) {
      field.type = 'enum'
      field.options = rule.enum.join('、')
    } else if (rule.type === 'array' && rule.items && Array.isArray(rule.items.enum)) {
      field.type = 'multiselect'
      field.options = rule.items.enum.join('、')
    } else if (rule.type === 'string' && DATE_FORMATS.includes(rule.format as never)) {
      field.type = 'date'
      field.options = String(rule.format)
    } else if (['string', 'number', 'integer', 'boolean'].includes(String(rule.type))) {
      field.type = rule.type as FormFieldType
    } else {
      field.type = 'unsupported'
    }

    fields.push(field)
  }

  return { fields, simple: fields.every((field) => field.type !== 'unsupported') }
}

/**
 * 字段表 → JSON Schema。
 *
 * 两条必须保住的语义：
 * 1. 先拿原有属性当底，**保留字段表管不到的约束**（minimum、pattern、additionalProperties…）；
 * 2. unsupported 行原样回写，不丢嵌套结构。
 */
export function applyFormFields(
  schema: JSONSchema | null | undefined,
  fields: FormFieldRow[],
): JSONSchema {
  const originals = schema?.properties || {}
  const properties: Record<string, JSONSchema> = {}
  const required: string[] = []

  fields.forEach((field) => {
    if (!field.key) return

    const rule: JSONSchema = { ...(originals[field.key] || {}) }

    if (field.type === 'unsupported') {
      properties[field.key] = rule
      return
    }

    delete rule.enum
    delete rule.format
    delete rule.items

    if (field.type === 'enum') {
      rule.type = 'string'
      rule.enum = splitOptions(field.options)
    } else if (field.type === 'multiselect') {
      rule.type = 'array'
      rule.items = { type: 'string', enum: splitOptions(field.options) }
    } else if (field.type === 'date') {
      rule.type = 'string'
      rule.format =
        field.options && DATE_FORMATS.includes(field.options as never) ? field.options : 'date'
    } else {
      rule.type = field.type
    }

    rule.title = field.title || field.key
    properties[field.key] = rule
    if (field.required) required.push(field.key)
  })

  const next: JSONSchema = { ...(schema || {}) }
  next.type = 'object'
  next.properties = properties
  if (required.length) next.required = required
  else delete next.required
  return next
}

/** 条件字段 → 显示名。画布与弹窗都靠它把 `approval_form.amount` 写成人话。 */
export function formFieldLabels(schema?: JSONSchema | null): Record<string, string> {
  const labels: Record<string, string> = {}
  formFieldsFromSchema(schema).fields.forEach((field) => {
    labels[`approval_form.${field.key}`] = field.title || field.key
  })
  return labels
}

/** 条件分支弹窗里的字段下拉：值统一带 approval_form 前缀。 */
export function conditionFieldOptions(
  schema?: JSONSchema | null,
): Array<{ value: string; label: string }> {
  return formFieldsFromSchema(schema)
    .fields.filter((field) => field.type !== 'unsupported')
    .map((field) => ({
      value: `approval_form.${field.key}`,
      label: `${field.title}（${formFieldTypeLabel(field.type)}）`,
    }))
}

/** 按字段类型造一份表单示例值，用于「按 Schema 生成示例」。 */
export function sampleFormFromSchema(schema?: JSONSchema | null): Record<string, unknown> {
  const sample: Record<string, unknown> = {}
  formFieldsFromSchema(schema).fields.forEach((field) => {
    if (field.type === 'number' || field.type === 'integer') sample[field.key] = 10000
    else if (field.type === 'boolean') sample[field.key] = true
    else if (field.type === 'date') sample[field.key] = '2026-09-30'
    else if (field.type === 'enum') sample[field.key] = splitOptions(field.options)[0] || ''
    else if (field.type === 'multiselect') sample[field.key] = []
    else sample[field.key] = '示例'
  })
  return sample
}

/** 新字段的默认键名：field1、field2 …（避开已有的）。 */
export function uniqueFieldKey(fields: Array<{ key: string }>): string {
  let index = fields.length + 1
  const used = new Set(fields.map((field) => field.key))
  while (used.has(`field${index}`)) index += 1
  return `field${index}`
}

/** 选项文本按顿号、逗号与空白切分。 */
export function splitOptions(text: string): string[] {
  return String(text || '')
    .split(/[、,，\s]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}
