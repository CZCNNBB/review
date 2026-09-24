import { describe, expect, it } from 'vitest'

import type { FormFieldRow } from '@/utils/schemaForm'
import {
  conditionText,
  conditionValueControl,
  operatorOptionsForField,
  typedConditionValue,
} from '@/utils/condition'

function field(type: FormFieldRow['type'], options = ''): FormFieldRow {
  return { key: 'k', title: '字段', required: false, type, options }
}

describe('比较方式按字段类型过滤', () => {
  it('数字与日期可以比大小，共 10 项', () => {
    expect(operatorOptionsForField(field('number'))).toHaveLength(10)
    expect(operatorOptionsForField(field('date')).map((item) => item.value)).toContain('GT')
  })

  it('文本只能判等、属于与判空，共 6 项', () => {
    const options = operatorOptionsForField(field('string')).map((item) => item.value)
    expect(options).toEqual(['EQ', 'NE', 'IN', 'NOT_IN', 'IS_EMPTY', 'NOT_EMPTY'])
  })

  it('布尔只能判等与判空', () => {
    expect(operatorOptionsForField(field('boolean')).map((item) => item.value)).toEqual([
      'EQ',
      'NE',
      'IS_EMPTY',
      'NOT_EMPTY',
    ])
  })

  it('没有字段时给通用的一组', () => {
    expect(operatorOptionsForField(null).map((item) => item.value)).toContain('EQ')
  })
})

describe('比较值按类型转换', () => {
  it('数字与整数转 Number，布尔认 true', () => {
    expect(typedConditionValue(field('number'), 'GT', '10000')).toBe(10000)
    expect(typedConditionValue(field('integer'), 'EQ', '3')).toBe(3)
    expect(typedConditionValue(field('boolean'), 'EQ', 'true')).toBe(true)
    expect(typedConditionValue(field('boolean'), 'EQ', 'false')).toBe(false)
  })

  it('文本原样返回并去掉首尾空格', () => {
    expect(typedConditionValue(field('string'), 'EQ', ' 宁波精工 ')).toBe('宁波精工')
  })

  it('IN / NOT_IN 解析 JSON 数组，单个值也包成数组', () => {
    expect(typedConditionValue(field('enum'), 'IN', '["A","B"]')).toEqual(['A', 'B'])
    // 解析成功但不是数组时包一层：单值 10000 → [10000]
    expect(typedConditionValue(field('number'), 'IN', '10000')).toEqual([10000])
    // 裸词不是合法 JSON（旧版同样报错，不是这里放宽的）
    expect(() => typedConditionValue(field('enum'), 'IN', 'A')).toThrow('不是合法的 JSON')
  })

  it('JSON 非法时抛出带中文前缀的错误', () => {
    expect(() => typedConditionValue(field('enum'), 'IN', '[A')).toThrow('比较值 不是合法的 JSON')
  })
})

describe('条件写成人话', () => {
  const labels = { 'approval_form.amount': '付款金额', 'approval_form.remark': '备注' }

  it('空条件返回空串', () => {
    expect(conditionText(null, labels)).toBe('')
  })

  it('普通比较给出「字段 符号 值」', () => {
    expect(
      conditionText({ field: 'approval_form.amount', operator: 'GT', value: 10000 }, labels),
    ).toBe('付款金额 > 10000')
  })

  it('判空类没有取值', () => {
    expect(conditionText({ field: 'approval_form.remark', operator: 'IS_EMPTY' }, labels)).toBe(
      '备注 为空',
    )
  })

  it('数组取值序列化成 JSON', () => {
    expect(
      conditionText({ field: 'approval_form.amount', operator: 'IN', value: ['A', 'B'] }, labels),
    ).toBe('付款金额 属于 ["A","B"]')
  })

  it('没有标签时退回字段名本身（去掉 approval_form 前缀）', () => {
    expect(conditionText({ field: 'approval_form.amount', operator: 'EQ', value: 1 })).toBe(
      'amount = 1',
    )
  })
})

describe('条件取值的控件选择', () => {
  it('判空类不需要取值控件', () => {
    expect(conditionValueControl(field('string'), 'IS_EMPTY')).toEqual({ kind: 'none' })
    expect(conditionValueControl(field('string'), 'NOT_EMPTY')).toEqual({ kind: 'none' })
  })

  it('枚举给下拉，布尔给是否，数字给数字框', () => {
    expect(conditionValueControl(field('enum', 'A、B'), 'EQ')).toEqual({
      kind: 'select',
      options: [
        { value: 'A', label: 'A' },
        { value: 'B', label: 'B' },
      ],
    })
    expect(conditionValueControl(field('boolean'), 'EQ')).toEqual({
      kind: 'select',
      options: [
        { value: 'true', label: '是' },
        { value: 'false', label: '否' },
      ],
    })
    expect(conditionValueControl(field('number'), 'GT')).toEqual({ kind: 'number' })
  })

  it('IN 用文本框，枚举会提示写 JSON 数组', () => {
    expect(conditionValueControl(field('enum', 'A、B'), 'IN')).toEqual({
      kind: 'text',
      placeholder: '多个取值写成 JSON 数组，例如 ["A","B"]',
    })
  })
})
