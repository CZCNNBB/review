import { describe, expect, it } from 'vitest'

import type { JSONSchema, NodeDefinition, UISchema } from '@/types/domain'
import {
  buildConfigForm,
  defaultConfigFor,
  nodeConfigSummary,
  nodeFormNote,
  pruneNodeConfig,
} from '@/utils/nodeConfigForm'

const APPROVAL_DEFINITION: Pick<NodeDefinition, 'config_schema_json' | 'ui_schema_json'> = {
  config_schema_json: {
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
          required: ['person_id'],
          properties: { person_id: { type: 'string', format: 'uuid' } },
        },
      },
    },
  },
  ui_schema_json: {
    approval_mode: { 'ui:widget': 'select' },
    approvers: { 'ui:widget': 'person-select' },
  },
}

const PERSON_OPTIONS = [
  { value: 'p1', label: '张三' },
  { value: 'p2', label: '李四' },
]

describe('按 Schema 生成初始配置', () => {
  it('default 优先，其次枚举第一项，再次空数组/对象/布尔', () => {
    const definition = {
      config_schema_json: {
        type: 'object',
        properties: {
          withDefault: { type: 'string', default: 'X' },
          mode: { type: 'string', enum: ['AND', 'OR'] },
          list: { type: 'array' },
          obj: { type: 'object' },
          flag: { type: 'boolean' },
          plain: { type: 'string' },
        },
      } as JSONSchema,
    }

    expect(defaultConfigFor(definition)).toEqual({
      withDefault: 'X',
      mode: 'AND',
      list: [],
      obj: {},
      flag: false,
    })
  })
})

describe('节点配置弹窗的表单描述', () => {
  it('把审批模式与审批人翻译成字段，并回填当前取值', () => {
    const form = buildConfigForm(
      APPROVAL_DEFINITION,
      { approval_mode: 'OR', approvers: [{ person_id: 'p2' }] },
      PERSON_OPTIONS,
    )

    expect(form.hasSchema).toBe(true)
    expect(form.fields.map((field) => field.name)).toEqual(['approval_mode', 'approvers'])
    expect(form.fields[0].label).toBe('审批模式 *')
    // 选人用专门的字段类型：DynamicForm 据此渲染可搜索、带部门标签的 PersonSelect
    expect(form.fields[1].type).toBe('person-select')

    // 回填：下拉要选中当前值，人员要选中已配的人
    expect(form.values.approval_mode).toBe('OR')
    expect(form.values.approvers).toEqual(['p2'])
  })

  it('没有配置过的枚举字段回填第一个选项，避免保存时被静默改掉', () => {
    const form = buildConfigForm(APPROVAL_DEFINITION, {}, PERSON_OPTIONS)
    expect(form.values.approval_mode).toBe('AND')
    expect(form.values.approvers).toEqual([])
  })

  it('提交时把人员选项转回 person_id 结构', () => {
    const form = buildConfigForm(APPROVAL_DEFINITION, {}, PERSON_OPTIONS)
    const config = form.fromForm({ approval_mode: 'OR', approvers: ['p1', 'p2'] })

    expect(config).toEqual({
      approval_mode: 'OR',
      approvers: [{ person_id: 'p1' }, { person_id: 'p2' }],
    })
  })

  it('数组/对象字段按 JSON 文本解析，非法时抛错', () => {
    const definition = {
      config_schema_json: {
        type: 'object',
        properties: { params: { type: 'object', title: '参数' } },
      } as JSONSchema,
      ui_schema_json: {} as UISchema,
    }

    const form = buildConfigForm(definition, { params: { a: 1 } }, [])
    expect(form.values.params).toBe('{\n  "a": 1\n}')
    expect(form.fromForm({ params: '{"b":2}' })).toEqual({ params: { b: 2 } })
    expect(() => form.fromForm({ params: '{bad' })).toThrow('参数 不是合法的 JSON')
  })

  it('没有配置项时 hasSchema 为 false', () => {
    const empty = { config_schema_json: { type: 'object', properties: {} }, ui_schema_json: {} }
    expect(buildConfigForm(empty, {}, []).hasSchema).toBe(false)
  })
})

describe('按节点定义清理失效配置', () => {
  it('定义里没有的配置项被丢掉并报出名字', () => {
    const node = { config: { approval_mode: 'AND', result_status: 'APPROVED' } }
    const definition = {
      config_schema_json: {
        type: 'object',
        properties: { approval_mode: { type: 'string' } },
      } as JSONSchema,
    }

    expect(pruneNodeConfig(node, definition)).toEqual({
      config: { approval_mode: 'AND' },
      dropped: ['result_status'],
    })
    // 原对象不动
    expect(node.config.result_status).toBe('APPROVED')
  })

  it('找不到定义时原样返回（宁可交给后端校验，也不要静默清空）', () => {
    expect(pruneNodeConfig({ config: { a: 1 } }, null).dropped).toEqual([])
  })
})

describe('节点卡片摘要', () => {
  it('人工审批给出模式与人数', () => {
    expect(
      nodeConfigSummary({ node_type: 'APPROVAL', config: { approval_mode: 'AND', approvers: [] } }),
    ).toBe('全部同意 · 0 位审批人')
    expect(
      nodeConfigSummary({
        node_type: 'APPROVAL',
        config: { approval_mode: 'OR', approvers: [{ person_id: 'p1' }] },
      }),
    ).toBe('任意一人同意 · 1 位审批人')
  })

  it('开始与结束节点用固定说法', () => {
    expect(nodeConfigSummary({ node_type: 'START', config: {} })).toBe('流程入口')
    expect(nodeConfigSummary({ node_type: 'END', config: {} })).toBe('流程完成')
    // 结束节点即使带着历史配置也还是「流程完成」
    expect(nodeConfigSummary({ node_type: 'END', config: { result_status: 'REJECTED' } })).toBe(
      '流程完成',
    )
  })

  it('其他类型按配置项平铺，最多两项', () => {
    expect(nodeConfigSummary({ node_type: 'X', config: {} })).toBe('未配置')
    expect(nodeConfigSummary({ node_type: 'X', config: { a: 1, b: 2, c: 3 } })).toBe('a: 1 · b: 2')
  })
})

describe('无配置节点的说明文案', () => {
  it('有 Schema 时不需要说明', () => {
    expect(nodeFormNote('APPROVAL', true)).toBeNull()
  })

  it('开始节点引导去配审批表单', () => {
    expect(nodeFormNote('START', false)).toEqual({
      text: expect.stringContaining('开始节点本身没有可配置项'),
      action: { kind: 'goto-form', label: '去配置表单字段' },
    })
  })

  it('条件分支引导去分支编辑器', () => {
    expect(nodeFormNote('CONDITION', false)?.action).toEqual({
      kind: 'goto-branch',
      label: '去配置分支',
      nodeId: '',
    })
  })

  it('结束节点只解释语义，不给跳转', () => {
    const note = nodeFormNote('END', false)
    expect(note?.text).toContain('走到这里就是审批通过')
    expect(note?.action).toBeUndefined()
  })
})
