import { describe, expect, it } from 'vitest'

import type { JSONSchema, UISchema } from '@/types/domain'
import { applyConfigFields, configFieldsFromSchema, isPersonItemSchema } from '@/utils/schemaConfig'
import {
  applyFormFields,
  conditionFieldOptions,
  formFieldLabels,
  formFieldsFromSchema,
  sampleFormFromSchema,
  splitOptions,
  uniqueFieldKey,
} from '@/utils/schemaForm'

const FORM_SCHEMA: JSONSchema = {
  type: 'object',
  properties: {
    amount: { type: 'number', title: '付款金额' },
    supplier_name: { type: 'string', title: '供应商' },
    pay_date: { type: 'string', format: 'date' },
    remark: { type: 'string' },
  },
  required: ['amount', 'supplier_name'],
}

describe('审批表单：Schema ⇄ 字段表', () => {
  it('解析出字段、标题、必填与类型', () => {
    const { fields, simple } = formFieldsFromSchema(FORM_SCHEMA)

    expect(simple).toBe(true)
    expect(fields.map((field) => `${field.key}:${field.type}${field.required ? '*' : ''}`)).toEqual(
      ['amount:number*', 'supplier_name:string*', 'pay_date:date', 'remark:string'],
    )
  })

  it('枚举与多选各自映射，选项用顿号连接', () => {
    const schema: JSONSchema = {
      type: 'object',
      properties: {
        level: { type: 'string', enum: ['NORMAL', 'URGENT'] },
        tags: { type: 'array', items: { type: 'string', enum: ['A', 'B'] } },
      },
    }
    const { fields } = formFieldsFromSchema(schema)

    expect(fields[0]).toMatchObject({ type: 'enum', options: 'NORMAL、URGENT' })
    expect(fields[1]).toMatchObject({ type: 'multiselect', options: 'A、B' })
  })

  it('嵌套对象标成 unsupported，并让调用方切高级模式', () => {
    const schema: JSONSchema = {
      type: 'object',
      properties: { payload: { type: 'object', properties: { inner: { type: 'string' } } } },
    }
    const { fields, simple } = formFieldsFromSchema(schema)

    expect(fields[0].type).toBe('unsupported')
    expect(simple).toBe(false)
  })

  it('往返转换保留字段表管不到的约束', () => {
    const schema: JSONSchema = {
      type: 'object',
      properties: {
        amount: { type: 'number', title: '付款金额', minimum: 100, pattern: '^\\d+$' },
        payload: { type: 'object', properties: { nested: { type: 'string' } } },
      },
      required: ['amount'],
      additionalProperties: false,
    }

    const { fields } = formFieldsFromSchema(schema)
    const next = applyFormFields(schema, fields)

    expect(next.properties?.amount).toMatchObject({
      minimum: 100,
      pattern: '^\\d+$',
      type: 'number',
    })
    expect(next.additionalProperties).toBe(false)
    // unsupported 的结构原样保留
    expect(next.properties?.payload.properties?.nested).toEqual({ type: 'string' })
    expect(next.required).toEqual(['amount'])
  })

  it('改类型会重写约束：单选 ↔ 多选 ↔ 文本', () => {
    const schema: JSONSchema = {
      type: 'object',
      properties: { level: { type: 'string', title: '级别', enum: ['A', 'B'] } },
    }
    const { fields } = formFieldsFromSchema(schema)

    fields[0].type = 'multiselect'
    fields[0].options = 'A、B、C'
    const asMulti = applyFormFields(schema, fields)
    expect(asMulti.properties?.level).toEqual({
      type: 'array',
      title: '级别',
      items: { type: 'string', enum: ['A', 'B', 'C'] },
    })

    fields[0].type = 'string'
    const asText = applyFormFields(schema, fields)
    expect(asText.properties?.level).toEqual({ type: 'string', title: '级别' })
  })

  it('必填项全删后 required 键要消失，而不是留个空数组', () => {
    const { fields } = formFieldsFromSchema(FORM_SCHEMA)
    fields.forEach((field) => {
      field.required = false
    })
    expect('required' in applyFormFields(FORM_SCHEMA, fields)).toBe(false)
  })

  it('字段名 → 条件下拉选项，带中文标题与类型', () => {
    expect(conditionFieldOptions(FORM_SCHEMA)).toEqual([
      { value: 'approval_form.amount', label: '付款金额（数字）' },
      { value: 'approval_form.supplier_name', label: '供应商（文本）' },
      { value: 'approval_form.pay_date', label: 'pay_date（日期）' },
      { value: 'approval_form.remark', label: 'remark（文本）' },
    ])
    expect(formFieldLabels(FORM_SCHEMA)).toMatchObject({
      'approval_form.amount': '付款金额',
      'approval_form.remark': 'remark',
    })
  })

  it('按 Schema 造示例值', () => {
    expect(sampleFormFromSchema(FORM_SCHEMA)).toEqual({
      amount: 10000,
      supplier_name: '示例',
      pay_date: '2026-09-30',
      remark: '示例',
    })
  })

  it('选项按顿号、逗号、空白切分并去空', () => {
    expect(splitOptions('A、B, C，D  E')).toEqual(['A', 'B', 'C', 'D', 'E'])
    expect(splitOptions('')).toEqual([])
  })

  it('新字段键名避开已有的', () => {
    expect(uniqueFieldKey([{ key: 'field1' }])).toBe('field2')
    // field2 已被占用时继续往后找
    expect(uniqueFieldKey([{ key: 'field2' }])).toBe('field3')
    expect(uniqueFieldKey([])).toBe('field1')
  })
})

describe('节点定义：Schema + uiSchema ⇄ 配置项表', () => {
  const SCHEMA: JSONSchema = {
    type: 'object',
    required: ['approval_mode', 'approvers'],
    properties: {
      approval_mode: { type: 'string', title: '审批模式', enum: ['AND', 'OR'] },
      approvers: {
        type: 'array',
        title: '审批人',
        minItems: 1,
        items: {
          type: 'object',
          additionalProperties: false,
          required: ['person_id'],
          properties: { person_id: { type: 'string', format: 'uuid' } },
        },
      },
    },
  }
  const UI: UISchema = {
    'ui:order': [],
    approval_mode: { 'ui:widget': 'select' },
    approvers: { 'ui:widget': 'person-select' },
  }

  it('识别人员选择器（认 ui:widget 也认 items 结构）', () => {
    const { fields, simple } = configFieldsFromSchema(SCHEMA, UI)
    expect(simple).toBe(true)
    expect(fields.map((field) => field.type)).toEqual(['enum', 'person-select'])
    expect(isPersonItemSchema(SCHEMA.properties?.approvers.items)).toBe(true)
    expect(isPersonItemSchema({ type: 'array', items: { type: 'string' } })).toBe(false)
  })

  it('往返转换保留 minItems 与根级 ui 规则，并丢掉孤立的 ui 配置', () => {
    const { fields } = configFieldsFromSchema(SCHEMA, UI)
    const { schema, uiSchema } = applyConfigFields(SCHEMA, UI, fields)

    expect(schema.properties?.approvers).toMatchObject({ type: 'array', minItems: 1 })
    expect(schema.required).toEqual(['approval_mode', 'approvers'])
    expect(uiSchema['ui:order']).toEqual([])
    expect(uiSchema.approvers).toEqual({ 'ui:widget': 'person-select' })

    // 删掉一个配置项后，它的 ui 配置不该留下
    const trimmed = applyConfigFields(SCHEMA, UI, fields.slice(0, 1))
    expect(trimmed.uiSchema.approvers).toBeUndefined()
    expect(trimmed.schema.properties?.approvers).toBeUndefined()
  })

  it('把文本项改成人员选择器会写出完整的 person_id 结构', () => {
    const schema: JSONSchema = {
      type: 'object',
      properties: { owner: { type: 'string', title: '负责人' } },
    }
    const { fields } = configFieldsFromSchema(schema, {})
    fields[0].type = 'person-select'

    const { schema: next, uiSchema } = applyConfigFields(schema, {}, fields)
    expect(next.properties?.owner).toMatchObject({ type: 'array', minItems: 1 })
    expect(isPersonItemSchema(next.properties?.owner.items)).toBe(true)
    expect(uiSchema.owner).toEqual({ 'ui:widget': 'person-select' })
  })
})
