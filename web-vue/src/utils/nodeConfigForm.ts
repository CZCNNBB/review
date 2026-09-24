import type { FlowNode, JSONSchema, NodeDefinition, NodeType, UISchema } from '@/types/domain'

import { parseJsonInput, stringifyJson } from './json'

/** 动态表单字段描述符。弹窗按它渲染控件，页面里不再手拼 HTML。 */
export interface DynamicFieldSpec {
  name: string
  label: string
  type: 'text' | 'number' | 'select' | 'multiselect' | 'textarea' | 'code' | 'checkbox' | 'note'
  options?: Array<{ value: string; label: string }>
  placeholder?: string
  hint?: string
  wide?: boolean
  required?: boolean
  checkboxLabel?: string
  /** note 字段的正文 */
  text?: string
  /** note 字段里的跳转按钮 */
  action?: NodeFormNoteAction
}

/** note 里的跳转按钮。旧版是塞进 HTML 字符串的 data-act 按钮，这里改成结构化数据。 */
export type NodeFormNoteAction =
  { kind: 'goto-form'; label: string } | { kind: 'goto-branch'; label: string; nodeId: string }

export interface BuiltConfigForm {
  fields: DynamicFieldSpec[]
  values: Record<string, unknown>
  fromForm: (formValues: Record<string, unknown>) => Record<string, unknown>
  hasSchema: boolean
}

export interface SelectOption {
  value: string
  label: string
}

/**
 * 把节点定义的 config_schema_json + ui_schema_json 翻译成弹窗字段，并提供反向转换。
 *
 * 与旧版的区别：人员选项改为**注入**（旧版闭包读全局 persons），这样它是纯函数，
 * 可以直接单测。
 */
export function buildConfigForm(
  definition: Pick<NodeDefinition, 'config_schema_json' | 'ui_schema_json'>,
  config: Record<string, unknown>,
  personOptions: SelectOption[] = [],
): BuiltConfigForm {
  const schema: JSONSchema = definition.config_schema_json || {}
  const uiSchema: UISchema = definition.ui_schema_json || {}
  const properties = schema.properties || {}
  const names = Object.keys(properties)
  const required = new Set(schema.required || [])

  const fields: DynamicFieldSpec[] = []
  const values: Record<string, unknown> = {}

  for (const name of names) {
    const rule = properties[name] || {}
    const widget = uiWidgetOf(uiSchema[name])
    const label = `${rule.title || name}${required.has(name) ? ' *' : ''}`
    const current = config[name]

    if (widget === 'person-select') {
      const itemKeys = rule.items?.required || []
      const itemKey = itemKeys[0] || 'person_id'
      fields.push({
        name,
        label,
        type: 'multiselect',
        options: personOptions,
        wide: true,
        hint: rule.description || '按住 Ctrl 或 Shift 多选',
      })
      values[name] = (Array.isArray(current) ? current : [])
        .map((item) => (item as Record<string, unknown> | null)?.[itemKey])
        .filter(Boolean)
    } else if (widget === 'textarea') {
      fields.push({ name, label, type: 'textarea', wide: true, hint: rule.description })
      values[name] = current === undefined || current === null ? '' : current
    } else if (Array.isArray(rule.enum)) {
      fields.push({
        name,
        label,
        type: 'select',
        options: rule.enum.map((value) => ({ value: String(value), label: String(value) })),
        hint: rule.description,
      })
      values[name] = current === undefined || current === null ? rule.enum[0] : current
    } else if (rule.type === 'boolean') {
      fields.push({
        name,
        label,
        type: 'checkbox',
        checkboxLabel: rule.description || '是',
      })
      values[name] = Boolean(current)
    } else if (rule.type === 'integer' || rule.type === 'number') {
      fields.push({ name, label, type: 'number', hint: rule.description })
      values[name] = current === undefined || current === null ? '' : current
    } else if (rule.type === 'array' || rule.type === 'object') {
      fields.push({
        name,
        label,
        type: 'code',
        wide: true,
        hint: rule.description || `${rule.type === 'array' ? '数组' : '对象'}，按 JSON 填写`,
      })
      values[name] =
        current === undefined ? (rule.type === 'array' ? '[]' : '{}') : stringifyJson(current)
    } else {
      fields.push({ name, label, type: 'text', hint: rule.description })
      values[name] = current === undefined || current === null ? '' : current
    }
  }

  /** 表单值 → 节点 config。取 JSON 的字段在这里解析，非法时抛错由弹窗内联展示。 */
  const fromForm = (formValues: Record<string, unknown>): Record<string, unknown> => {
    const next: Record<string, unknown> = {}
    for (const name of names) {
      const rule = properties[name] || {}
      const widget = uiWidgetOf(uiSchema[name])
      const raw = formValues[name]

      if (widget === 'person-select') {
        const itemKey = ((rule.items?.required || [])[0] as string) || 'person_id'
        next[name] = (Array.isArray(raw) ? raw : []).map((value) => ({ [itemKey]: value }))
      } else if (widget === 'textarea') {
        next[name] = raw
      } else if (rule.type === 'array' || rule.type === 'object') {
        next[name] = parseJsonInput(raw, rule.title || name)
      } else if (rule.type === 'integer' || rule.type === 'number') {
        next[name] = raw === '' || raw === null || raw === undefined ? null : Number(raw)
      } else if (rule.type === 'boolean') {
        next[name] = Boolean(raw)
      } else {
        next[name] = raw
      }
    }
    return next
  }

  return { fields, values, fromForm, hasSchema: names.length > 0 }
}

/** ui_schema 里某一项如果是对象就取出来，其他形状一律当空。 */
function uiWidgetOf(value: unknown): unknown {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return (value as Record<string, unknown>)['ui:widget']
  }
  return undefined
}

/** 按节点定义的 Schema 生成初始配置：default 优先，其次枚举第一项，再次空数组/对象/布尔。 */
export function defaultConfigFor(
  definition: Pick<NodeDefinition, 'config_schema_json'>,
): Record<string, unknown> {
  const properties = definition.config_schema_json?.properties || {}
  const config: Record<string, unknown> = {}

  for (const [name, rule] of Object.entries(properties)) {
    if (rule.default !== undefined) config[name] = rule.default
    else if (Array.isArray(rule.enum) && rule.enum.length) config[name] = rule.enum[0]
    else if (rule.type === 'array') config[name] = []
    else if (rule.type === 'object') config[name] = {}
    else if (rule.type === 'boolean') config[name] = false
  }

  return config
}

/**
 * 节点定义是配置项的唯一来源：定义里已经删掉的配置项不再留在编辑器里，
 * 否则保存会被后端校验拦下，而界面上根本没有地方去删它。
 * 返回被清理掉的字段名，调用方据此提示一次。
 */
export function pruneNodeConfig(
  node: Pick<FlowNode, 'config'>,
  definition?: Pick<NodeDefinition, 'config_schema_json'> | null,
): { config: Record<string, unknown>; dropped: string[] } {
  const config: Record<string, unknown> = { ...(node.config || {}) }

  // 定义找不到时（被删或没加载出来）不能按"定义里什么都没有"来清配置，
  // 那会把节点配置整份抹掉。宁可原样交给后端校验，也不要静默丢数据。
  if (!definition) return { config, dropped: [] }

  const properties = definition.config_schema_json?.properties || {}
  const dropped: string[] = []

  Object.keys(config).forEach((name) => {
    if (!(name in properties)) {
      delete config[name]
      dropped.push(name)
    }
  })

  return { config, dropped }
}

/** 节点卡片上的配置摘要。 */
export function nodeConfigSummary(node: Pick<FlowNode, 'node_type' | 'config'>): string {
  const config = node.config || {}

  if (node.node_type === 'APPROVAL' && (config.approval_mode || config.approvers)) {
    const mode = (config.approval_mode as string) || '—'
    const count = Array.isArray(config.approvers) ? config.approvers.length : 0
    const text = mode === 'AND' ? '全部同意' : mode === 'OR' ? '任意一人同意' : mode
    return `${text} · ${count} 位审批人`
  }
  if (node.node_type === 'END') return '流程完成'
  if (node.node_type === 'START') return '流程入口'

  const entries = Object.entries(config).filter(([, value]) => {
    if (value === '' || value === null || value === undefined) return false
    return !(Array.isArray(value) && !value.length)
  })

  if (!entries.length) return '未配置'
  return entries
    .slice(0, 2)
    .map(([name, value]) =>
      typeof value === 'object' ? `${name}: ${stringifyJson(value)}` : `${name}: ${value}`,
    )
    .join(' · ')
}

/**
 * 没有 Schema 的节点在配置弹窗里给一段说明。
 *
 * 旧版这里返回的是**带 `<button data-act>` 的 HTML 字符串**，靠全局事件委托生效。
 * Vue 里禁止 v-html 渲染交互元素，所以改成结构化数据，由弹窗渲染真按钮。
 */
export function nodeFormNote(
  nodeType: NodeType,
  hasSchema: boolean,
): { text: string; action?: NodeFormNoteAction } | null {
  if (hasSchema) return null

  if (nodeType === 'START') {
    return {
      text: '开始节点本身没有可配置项。这条流程要收集哪些数据（金额、供应商这类）在下面的「审批表单」里定义。',
      action: { kind: 'goto-form', label: '去配置表单字段' },
    }
  }
  if (nodeType === 'CONDITION') {
    return {
      text: '条件分支的规则不在这个窗口里配。点画布上节点卡片里的分支行，或点这里打开分支编辑器，那里可以增删条件和调整顺序。每条分支去哪，关掉窗口后从卡片上对应那一行的圆点拉线到目标节点。',
      action: { kind: 'goto-branch', label: '去配置分支', nodeId: '' },
    }
  }
  if (nodeType === 'END') {
    return {
      text: '结束节点没有配置项。走到这里就是审批通过、流程完成；审批被拒绝时实例在审批人点拒绝的那一刻就结束了，不会走到结束节点。',
    }
  }
  return { text: '这个节点没有可配置项。' }
}
