import type { Condition } from '@/types/domain'

import { parseJsonInput } from './json'
import type { FormFieldRow } from './schemaForm'

/** 比较符。symbol 是写成人话时用的符号。 */
export interface OperatorSpec {
  value: string
  label: string
  symbol: string
}

export const OPERATORS: readonly OperatorSpec[] = [
  { value: 'EQ', label: '等于', symbol: '=' },
  { value: 'NE', label: '不等于', symbol: '≠' },
  { value: 'GT', label: '大于', symbol: '>' },
  { value: 'GTE', label: '大于等于', symbol: '≥' },
  { value: 'LT', label: '小于', symbol: '<' },
  { value: 'LTE', label: '小于等于', symbol: '≤' },
  { value: 'IN', label: '属于', symbol: '属于' },
  { value: 'NOT_IN', label: '不属于', symbol: '不属于' },
  { value: 'IS_EMPTY', label: '为空', symbol: '为空' },
  { value: 'NOT_EMPTY', label: '不为空', symbol: '不为空' },
]

/** 能比较大小的字段类型，决定了下拉里要不要给 > < 这些算子。 */
export const ORDERABLE_FIELD_TYPES = ['number', 'integer', 'date']

export const NO_VALUE_OPERATORS = ['IS_EMPTY', 'NOT_EMPTY']

export function operatorByValue(value: string): OperatorSpec | undefined {
  return OPERATORS.find((item) => item.value === value)
}

/**
 * 按字段类型给出可用的比较符。
 * 布尔字段只能判等与判空；数字和日期可以比大小；文本类只能判等、属于、判空。
 */
export function operatorOptionsForField(
  field?: FormFieldRow | null,
): Array<{ value: string; label: string }> {
  const orderable = Boolean(field && ORDERABLE_FIELD_TYPES.includes(field.type))
  const names =
    field && field.type === 'boolean'
      ? ['EQ', 'NE', 'IS_EMPTY', 'NOT_EMPTY']
      : orderable
        ? ['EQ', 'NE', 'GT', 'GTE', 'LT', 'LTE', 'IN', 'NOT_IN', 'IS_EMPTY', 'NOT_EMPTY']
        : ['EQ', 'NE', 'IN', 'NOT_IN', 'IS_EMPTY', 'NOT_EMPTY']

  return names.map((name) => {
    const operator = operatorByValue(name) as OperatorSpec
    return { value: operator.value, label: `${operator.label}（${operator.value}）` }
  })
}

/**
 * 比较值按字段类型转成对应的 JSON 类型，后端按类型逐项比对。
 * IN / NOT_IN 写的是 JSON 数组文本；布尔认 'true'；数字与整数转 Number。
 */
export function typedConditionValue(
  field: FormFieldRow | null | undefined,
  operator: string,
  raw: unknown,
): unknown {
  const text = String(raw === undefined || raw === null ? '' : raw).trim()

  if (operator === 'IN' || operator === 'NOT_IN') {
    const parsed = parseJsonInput(text, '比较值')
    return Array.isArray(parsed) ? parsed : [parsed]
  }
  if (!field) return text
  if (field.type === 'boolean') return text === 'true'
  if (field.type === 'number' || field.type === 'integer') return Number(text)
  return text
}

/**
 * 把一条条件写成人话：`金额 > 10000`、`供应商 属于 ["A","B"]`、`备注 为空`。
 * labels 是 `approval_form.amount → 付款金额` 的映射，来自审批表单 Schema。
 */
export function conditionText(
  condition?: Condition | null,
  labels?: Record<string, string>,
): string {
  if (!condition) return ''

  const operator = operatorByValue(condition.operator) || { symbol: condition.operator }
  const name =
    (labels && labels[condition.field]) || condition.field.replace(/^approval_form\./, '')

  if (NO_VALUE_OPERATORS.includes(condition.operator)) return `${name} ${operator.symbol}`

  // 取值用紧凑 JSON：这条文案渲染在单行小药丸里，缩进换行会被截断成半截。
  // （旧版用的是带缩进的 formatJson，属于显示瑕疵，这里改掉了。）
  const value =
    condition.value === undefined
      ? ''
      : typeof condition.value === 'string'
        ? condition.value
        : JSON.stringify(condition.value)
  return `${name} ${operator.symbol} ${value}`
}

/** 条件取值该用什么控件。旧版是直接拼 HTML，这里只描述"用什么"，由组件渲染。 */
export type ConditionValueControl =
  | { kind: 'none' }
  | { kind: 'select'; options: Array<{ value: string; label: string }> }
  | { kind: 'number' }
  | { kind: 'text'; placeholder: string }

export function conditionValueControl(
  field: FormFieldRow | null | undefined,
  operator: string,
): ConditionValueControl {
  if (!field || NO_VALUE_OPERATORS.includes(operator)) return { kind: 'none' }

  if (operator === 'IN' || operator === 'NOT_IN') {
    return {
      kind: 'text',
      placeholder:
        field.type === 'enum' || field.type === 'multiselect'
          ? '多个取值写成 JSON 数组，例如 ["A","B"]'
          : '["A","B"]',
    }
  }
  if (field.type === 'enum') {
    return {
      kind: 'select',
      options: splitFieldOptions(field.options).map((value) => ({ value, label: value })),
    }
  }
  if (field.type === 'boolean') {
    return {
      kind: 'select',
      options: [
        { value: 'true', label: '是' },
        { value: 'false', label: '否' },
      ],
    }
  }
  if (field.type === 'number' || field.type === 'integer') return { kind: 'number' }
  return { kind: 'text', placeholder: '要比较的内容' }
}

/** 选项文本按顿号、逗号与空白切分（与 schemaForm.splitOptions 同规则，这里避免循环依赖）。 */
function splitFieldOptions(text: string): string[] {
  return String(text || '')
    .split(/[、,，\s]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}
