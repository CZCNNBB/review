import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import type { ProcessGraph } from '@/api/types'
import { useVersionEditorStore } from '@/stores/versionEditor'
import type { NodeDefinition } from '@/types/domain'

// 工作副本的契约测试：不挂任何组件，直接在 store 上验证，
// 这样"切页签不丢改动""保存带 revision"这类规则改一行就有反馈。

const DEFINITIONS: NodeDefinition[] = [
  {
    id: 'def-start',
    node_type: 'START',
    name: '开始',
    config_schema_json: { type: 'object', properties: {} },
    ui_schema_json: {},
    status: 'ENABLED',
  },
  {
    id: 'def-approval',
    node_type: 'APPROVAL',
    name: '人工审批',
    config_schema_json: {
      type: 'object',
      required: ['approval_mode', 'approvers'],
      properties: {
        approval_mode: { type: 'string', title: '审批模式', enum: ['AND', 'OR'] },
        approvers: { type: 'array', title: '审批人' },
      },
    },
    ui_schema_json: { approvers: { 'ui:widget': 'person-select' } },
    status: 'ENABLED',
  },
  {
    id: 'def-condition',
    node_type: 'CONDITION',
    name: '条件分支',
    config_schema_json: { type: 'object', properties: {} },
    ui_schema_json: {},
    status: 'ENABLED',
  },
]

function graphOf(overrides: Partial<ProcessGraph> = {}): ProcessGraph {
  return {
    process_id: 'p1',
    version_id: 'v1',
    version_no: 3,
    version_status: 'DRAFT',
    revision: 7,
    name: '付款审批流程',
    description: '金额超过 1 万元的付款申请需要总经理审批。',
    form_schema: {
      type: 'object',
      properties: { amount: { type: 'number', title: '付款金额' } },
      required: ['amount'],
    },
    form_ui_schema: {},
    orchestration: {
      connections: [
        { source_node_id: 'n1', target_node_id: 'n2' },
        { source_node_id: 'n2', target_node_id: 'n3' },
      ],
    },
    nodes: [
      {
        id: 'n1',
        node_definition_id: 'def-start',
        node_type: 'START',
        node_definition_name: '开始',
        name: '开始',
        config: {},
        position: { x: 64, y: 64 },
      },
      {
        id: 'n2',
        node_definition_id: 'def-approval',
        node_type: 'APPROVAL',
        node_definition_name: '人工审批',
        name: '财务审批',
        config: { approval_mode: 'AND', approvers: [] },
        position: { x: 300, y: 64 },
      },
      {
        id: 'n3',
        node_definition_id: 'def-condition',
        node_type: 'CONDITION',
        node_definition_name: '条件分支',
        name: '按金额分流',
        config: {},
        position: { x: 560, y: 64 },
      },
    ],
    created_at: '2026-09-24T00:00:00Z',
    updated_at: '2026-09-24T00:00:00Z',
    published_at: null,
    ...overrides,
  }
}

describe('版本编辑器工作副本', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('载入整图后填充状态，并清掉定义里已下线的配置项', () => {
    const store = useVersionEditorStore()
    const graph = graphOf()
    // 老草稿里结束节点还带着下线过的字段
    graph.nodes[1].config = { approval_mode: 'AND', approvers: [], result_status: 'APPROVED' }

    store.loadFromGraph(graph, DEFINITIONS)

    expect(store.versionId).toBe('v1')
    expect(store.revision).toBe(7)
    expect(store.editable).toBe(true)
    expect(store.droppedConfigFields).toEqual(['result_status'])
    expect(store.nodes[1].config).not.toHaveProperty('result_status')
  })

  it('契约①：切页签、开弹窗这类重渲染都不丢未保存改动', () => {
    const store = useVersionEditorStore()
    store.loadFromGraph(graphOf(), DEFINITIONS)

    const added = store.addNode(DEFINITIONS[1])
    store.activeTab = 'raw'
    store.formAdvanced = true

    // 只是换页签与开关高级模式，节点还在
    expect(store.nodes).toHaveLength(4)
    expect(store.nodes.some((node) => node.id === added.id)).toBe(true)
    expect(store.dirty).toBe(true)

    // 真正丢弃只有两条路：reset()（离开路由或保存成功）
    store.reset()
    expect(store.nodes).toHaveLength(0)
    expect(store.loaded).toBe(false)
  })

  it('契约②：保存载荷原样带上 revision，且只提交后端认识的节点字段', () => {
    const store = useVersionEditorStore()
    store.loadFromGraph(graphOf(), DEFINITIONS)

    const payload = store.buildPayload()

    expect(payload.revision).toBe(7)
    expect(payload.nodes[0]).toEqual({
      id: 'n1',
      node_definition_id: 'def-start',
      name: '开始',
      config: {},
      position: { x: 64, y: 64 },
    })
    expect(payload.orchestration.connections).toHaveLength(2)
    expect(payload.form_schema.required).toEqual(['amount'])
  })

  it('契约③：分支编辑器结果整体重建该节点出线，其余连线顺序不变', () => {
    const store = useVersionEditorStore()
    store.loadFromGraph(graphOf(), DEFINITIONS)

    // 给条件分支节点加两条分支，最后一条是兜底
    store.setConnections([
      { source_node_id: 'n1', target_node_id: 'n2' },
      { source_node_id: 'n2', target_node_id: 'n3' },
    ])
    store.applyBranchResult('n3', [
      {
        target_node_id: 'n2',
        condition: { field: 'approval_form.amount', operator: 'GT', value: 10000 },
      },
      { target_node_id: 'n1', condition: null },
    ])

    const outgoing = store.connections.filter((item) => item.source_node_id === 'n3')
    expect(outgoing).toHaveLength(2)
    expect(outgoing[0].condition?.value).toBe(10000)
    // 契约③：最后一条恒为「其余情况」，连 condition 字段都不该有
    expect(outgoing[1].condition).toBeUndefined()
    // 其他节点的连线原样保留
    expect(store.connections.slice(0, 2)).toEqual([
      { source_node_id: 'n1', target_node_id: 'n2' },
      { source_node_id: 'n2', target_node_id: 'n3' },
    ])
  })

  it('契约⑦：已发布版本不可编辑', () => {
    const store = useVersionEditorStore()
    store.loadFromGraph(graphOf({ version_status: 'PUBLISHED' }), DEFINITIONS)
    expect(store.editable).toBe(false)
  })

  it('删除节点会连带走掉挂在它身上的连线', () => {
    const store = useVersionEditorStore()
    store.loadFromGraph(graphOf(), DEFINITIONS)

    store.removeNode('n2')

    expect(store.nodes.map((node) => node.id)).toEqual(['n1', 'n3'])
    expect(store.connections).toHaveLength(0)
  })

  it('自动排版写回互不重复的坐标', () => {
    const store = useVersionEditorStore()
    store.loadFromGraph(graphOf(), DEFINITIONS)
    store.setNodePosition('n2', { x: 64, y: 64 })

    store.autoLayout()

    const keys = store.nodes.map((node) => `${node.position.x}:${node.position.y}`)
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('高级模式下以文本框内容为 Schema 权威来源', () => {
    const store = useVersionEditorStore()
    store.loadFromGraph(graphOf(), DEFINITIONS)

    store.formAdvanced = true
    store.formSchemaText = '{"type":"object","properties":{"note":{"type":"string"}}}'

    expect(store.buildPayload().form_schema.properties).toHaveProperty('note')

    // 非法 JSON 直接挡下保存
    store.formSchemaText = '{oops'
    expect(() => store.buildPayload()).toThrow('审批表单 Schema 不是合法的 JSON')
  })

  it('节点配置摘要与字段标签跟着 Schema 走', () => {
    const store = useVersionEditorStore()
    store.loadFromGraph(graphOf(), DEFINITIONS)
    expect(store.fieldLabels['approval_form.amount']).toBe('付款金额')
  })
})
