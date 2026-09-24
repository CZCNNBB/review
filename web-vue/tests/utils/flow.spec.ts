import { describe, expect, it } from 'vitest'

import type { FlowConnection, FlowNode } from '@/types/domain'
import {
  branchRowState,
  buildBranchConditions,
  applyBranchDialogResult,
  canConnectPlain,
  connectBranchTo,
  flowNodeWarning,
  isDragGesture,
} from '@/utils/flowBranch'
import { buildCanvasModel } from '@/utils/flowCanvasModel'
import { createFlowGeometry, flowStageSize } from '@/utils/flowGeometry'
import { defaultPositionFor, flowNeedsLayout, layoutNodes } from '@/utils/flowLayout'

function node(id: string, type: string, x: number, y: number, name = id): FlowNode {
  return {
    id,
    node_definition_id: `def-${type}`,
    node_type: type,
    node_definition_name: name,
    name,
    config: {},
    position: { x, y },
  }
}

const CONDITION: FlowNode = node('condition', 'CONDITION', 520, 150, '条件分支')
const TARGET_A: FlowNode = node('a', 'APPROVAL', 900, 100, '总经理审批')
const TARGET_B: FlowNode = node('b', 'END', 900, 300, '审批通过')
const START: FlowNode = node('start', 'START', 100, 150, '开始')

describe('画布几何', () => {
  it('条件分支的每条线从自己那一行的出口出发', () => {
    const connections: FlowConnection[] = [
      {
        source_node_id: 'condition',
        target_node_id: 'a',
        condition: { field: 'f', operator: 'GT', value: 1 },
      },
      { source_node_id: 'condition', target_node_id: 'b' },
    ]
    const geometry = createFlowGeometry([CONDITION, TARGET_A, TARGET_B], connections)

    // 卡片左上角 (520,150)，宽 232 → 出口 x = 752；第一行 y = 150 + 42 + 14 = 206
    expect(geometry.startOf(connections[0])).toEqual({ x: 752, y: 206 })
    expect(geometry.startOf(connections[1])).toEqual({ x: 752, y: 234 })
    expect(geometry.edgeOf(connections[0])?.d.startsWith('M 752 206 C')).toBe(true)
  })

  it('普通节点从右侧中点出发，结束节点从左侧中点进入', () => {
    const connections: FlowConnection[] = [{ source_node_id: 'start', target_node_id: 'a' }]
    const geometry = createFlowGeometry([START, TARGET_A], connections)

    expect(geometry.startOf(connections[0])).toEqual({ x: 284, y: 185 })
    expect(geometry.endOf(TARGET_A)).toEqual({ x: 900, y: 135 })
  })

  it('条件分支卡片的高度随分支数变化，兜底多留一行「新增分支」', () => {
    const geometry = createFlowGeometry([CONDITION, TARGET_A, TARGET_B], [])
    // 一行分支都没有时也要留两行：一行兜底 + 一行「新增分支」→ 42 + 2*28
    expect(geometry.sizeOf(CONDITION).height).toBe(98)

    const withTwo = createFlowGeometry(
      [CONDITION, TARGET_A, TARGET_B],
      [
        { source_node_id: 'condition', target_node_id: 'a' },
        { source_node_id: 'condition', target_node_id: 'b' },
      ],
    )
    expect(withTwo.sizeOf(CONDITION).height).toBe(42 + 3 * 28)
  })

  it('拖动中的临时坐标只影响被覆盖的那个节点', () => {
    const connections: FlowConnection[] = [{ source_node_id: 'start', target_node_id: 'a' }]
    const overrides = new Map([['start', { x: 400, y: 400 }]])
    const geometry = createFlowGeometry([START, TARGET_A], connections, overrides)

    expect(geometry.startOf(connections[0])).toEqual({ x: 584, y: 435 })
    expect(geometry.endOf(TARGET_A)).toEqual({ x: 900, y: 135 })
  })

  it('画布尺寸有下限，内容多时按内容外扩', () => {
    expect(flowStageSize([START], [])).toEqual({ width: 980, height: 520 })
    const wide = flowStageSize([node('far', 'END', 3000, 2000)], [])
    expect(wide.width).toBe(3000 + 184 + 64)
    expect(wide.height).toBe(2000 + 70 + 64)
  })
})

describe('分支阶梯规则', () => {
  const nodes = [CONDITION]
  const first: FlowConnection = {
    source_node_id: 'condition',
    target_node_id: 'a',
    condition: { field: 'approval_form.amount', operator: 'GT', value: 10000 },
  }
  const last: FlowConnection = { source_node_id: 'condition', target_node_id: 'b' }

  it('合法的阶梯没有任何问题', () => {
    const good = [first, last]
    expect(branchRowState(first, nodes, good).problem).toBeNull()
    expect(branchRowState(last, nodes, good).problem).toBeNull()
    expect(branchRowState(last, nodes, good).isLast).toBe(true)
  })

  it('最后一条带条件要报错：它是「其余情况」', () => {
    const badLast = [first, { ...last, condition: { field: 'x', operator: 'EQ', value: 1 } }]
    expect(branchRowState(badLast[1], nodes, badLast).problem).toBe(
      '最后一条是「其余情况」，不能配条件',
    )
  })

  it('前面一条没配条件要报错', () => {
    const badFirst = [{ source_node_id: 'condition', target_node_id: 'a' }, last]
    expect(branchRowState(badFirst[0], nodes, badFirst).problem).toBe('这条分支还没有配条件')
  })

  it('普通节点的连线不套用阶梯规则', () => {
    const approval = node('approval', 'APPROVAL', 0, 0)
    const connection: FlowConnection = { source_node_id: 'approval', target_node_id: 'b' }
    expect(branchRowState(connection, [approval], [connection]).problem).toBeNull()
  })
})

describe('卡片上的提醒', () => {
  it('条件分支：没分支 / 没接去向 / 没配完', () => {
    expect(flowNodeWarning(CONDITION, [CONDITION], [])).toBe('还没有分支')

    const dangling: FlowConnection[] = [{ source_node_id: 'condition', target_node_id: null }]
    expect(flowNodeWarning(CONDITION, [CONDITION], dangling)).toBe('分支未接去向')

    const incomplete: FlowConnection[] = [
      { source_node_id: 'condition', target_node_id: 'a' },
      { source_node_id: 'condition', target_node_id: 'b' },
    ]
    expect(flowNodeWarning(CONDITION, [CONDITION], incomplete)).toBe('分支未配完')
  })

  it('普通节点：没有去向 / 多条去向 / 去向带条件', () => {
    const approval = node('approval', 'APPROVAL', 0, 0)
    expect(flowNodeWarning(approval, [approval], [])).toBe('还没有去向')

    const two: FlowConnection[] = [
      { source_node_id: 'approval', target_node_id: 'a' },
      { source_node_id: 'approval', target_node_id: 'b' },
    ]
    expect(flowNodeWarning(approval, [approval], two)).toBe('只能有一条去向')

    const withCondition: FlowConnection[] = [
      {
        source_node_id: 'approval',
        target_node_id: 'a',
        condition: { field: 'f', operator: 'EQ', value: 1 },
      },
    ]
    expect(flowNodeWarning(approval, [approval], withCondition)).toBe('去向不能带条件')
  })

  it('结束节点不需要出线，不给提醒', () => {
    const end = node('end', 'END', 0, 0)
    expect(flowNodeWarning(end, [end], [])).toBeNull()
  })
})

describe('普通节点拉线规则（契约④）', () => {
  it('重复连线被拒', () => {
    const connections: FlowConnection[] = [{ source_node_id: 'a', target_node_id: 'b' }]
    expect(canConnectPlain(connections, 'a', 'b')).toEqual({ ok: false, reason: 'duplicate' })
  })

  it('已有出线就不许再拉：分流要走条件分支节点', () => {
    const connections: FlowConnection[] = [{ source_node_id: 'a', target_node_id: 'b' }]
    expect(canConnectPlain(connections, 'a', 'c')).toEqual({ ok: false, reason: 'multi-out' })
  })

  it('没有出线时可以连', () => {
    expect(canConnectPlain([], 'a', 'b')).toEqual({ ok: true })
  })
})

describe('从分支行拉线', () => {
  it('新分支插在「其余情况」之前，并且需要补条件', () => {
    const connections: FlowConnection[] = [
      { source_node_id: 'condition', target_node_id: 'a' },
      { source_node_id: 'condition', target_node_id: 'b' },
    ]
    const result = connectBranchTo(connections, 'condition', 'new', 'c')

    expect(result).toEqual({ created: true, needsCondition: true })
    expect(connections.map((item) => item.target_node_id)).toEqual(['a', 'c', 'b'])
  })

  it('第一条分支就是兜底，不要求配条件', () => {
    const connections: FlowConnection[] = []
    expect(connectBranchTo(connections, 'condition', 'new', 'a')).toEqual({
      created: true,
      needsCondition: false,
    })
    expect(connections).toHaveLength(1)
  })

  it('给某一行重新定去向：只改目标，不新增连线', () => {
    const connections: FlowConnection[] = [
      {
        source_node_id: 'condition',
        target_node_id: null,
        condition: { field: 'f', operator: 'EQ', value: 1 },
      },
    ]
    const result = connectBranchTo(connections, 'condition', 0, 'b')
    expect(result).toEqual({ created: false, needsCondition: false })
    expect(connections).toHaveLength(1)
    expect(connections[0].target_node_id).toBe('b')
    // 条件原样保留
    expect(connections[0].condition).toEqual({ field: 'f', operator: 'EQ', value: 1 })
  })

  it('拖到同一个目标没有变化', () => {
    const connections: FlowConnection[] = [{ source_node_id: 'condition', target_node_id: 'a' }]
    expect(connectBranchTo(connections, 'condition', 0, 'a')).toBeNull()
  })
})

describe('分支编辑器提交（契约③）', () => {
  const fieldOf = () =>
    ({ key: 'amount', title: '付款金额', required: false, type: 'number', options: '' }) as never

  it('最后一条恒为「其余情况」，即使草稿里带了条件', () => {
    const result = buildBranchConditions(
      [
        {
          target_node_id: 'a',
          condition: { field: 'approval_form.amount', operator: 'GT', value: '10000' },
        },
        {
          target_node_id: 'b',
          condition: { field: 'approval_form.amount', operator: 'LT', value: '1' },
        },
      ],
      fieldOf,
    )

    expect('built' in result).toBe(true)
    if (!('built' in result)) return
    expect(result.built).toHaveLength(2)
    expect(result.built[1].condition).toBeNull()
    // 取值按字段类型转换
    expect(result.built[0].condition?.value).toBe(10000)
  })

  it('中间一行没配字段时报错，并指出是第几条', () => {
    const result = buildBranchConditions(
      [
        { target_node_id: 'a', condition: { field: '', operator: 'EQ', value: '' } },
        { target_node_id: 'b', condition: null },
      ],
      fieldOf,
    )

    expect('error' in result && result.error).toContain('条件 1')
  })

  it('没接去向的分支把目标留空', () => {
    const result = buildBranchConditions([{ target_node_id: null, condition: null }], fieldOf)
    expect('built' in result && result.built[0].target_node_id).toBeNull()
  })

  it('重建出线时其他节点的连线原样保留', () => {
    const connections: FlowConnection[] = [
      { source_node_id: 'start', target_node_id: 'condition' },
      { source_node_id: 'condition', target_node_id: 'old' },
    ]
    const next = applyBranchDialogResult(connections, 'condition', [
      { target_node_id: 'a', condition: { field: 'f', operator: 'EQ', value: 1 } },
      { target_node_id: 'b', condition: null },
    ])

    expect(next).toHaveLength(3)
    expect(next[0]).toEqual({ source_node_id: 'start', target_node_id: 'condition' })
    expect(next[1].target_node_id).toBe('a')
    expect(next[2].condition).toBeUndefined()
  })
})

describe('自动排版', () => {
  it('按层摆放且坐标互不重复', () => {
    const nodes = [
      node('start', 'START', 0, 0, '开始'),
      node('a', 'APPROVAL', 0, 0, '财务审批'),
      node('b', 'END', 0, 0, '结束'),
      node('orphan', 'APPROVAL', 0, 0, '孤立节点'),
    ]
    const connections: FlowConnection[] = [
      { source_node_id: 'start', target_node_id: 'a' },
      { source_node_id: 'a', target_node_id: 'b' },
    ]
    const laid = layoutNodes(nodes, connections)

    const keys = laid.map((item) => `${item.position.x}:${item.position.y}`)
    expect(new Set(keys).size).toBe(keys.length)

    // 原数组没被改动
    expect(nodes[0].position).toEqual({ x: 0, y: 0 })
    // 开始 → 审批 → 结束 依次向右
    expect(laid[0].position.x).toBeLessThan(laid[1].position.x)
    expect(laid[1].position.x).toBeLessThan(laid[2].position.x)
  })

  it('坐标全零或重复时提示需要排版', () => {
    expect(flowNeedsLayout([START])).toBe(false)
    expect(flowNeedsLayout([START, node('x', 'END', 0, 0)])).toBe(true)
    expect(flowNeedsLayout([node('a', 'END', 10, 10), node('b', 'END', 10, 10)])).toBe(true)
    expect(flowNeedsLayout([node('a', 'END', 10, 10), node('b', 'END', 20, 10)])).toBe(false)
  })

  it('新增节点落在最右列的右边', () => {
    const position = defaultPositionFor([node('a', 'END', 500, 100)])
    expect(position.x).toBe(500 + 184 + 88)
    // y 按已有节点数错开三行：64 + (1 % 3) * 112
    expect(position.y).toBe(176)
  })
})

describe('拖动手势（契约⑤）', () => {
  it('位移不超过 2px 视为点击', () => {
    expect(isDragGesture(0, 0)).toBe(false)
    expect(isDragGesture(2, 2)).toBe(false)
    expect(isDragGesture(3, 0)).toBe(true)
    expect(isDragGesture(0, -3)).toBe(true)
  })
})

describe('画布视图模型', () => {
  const connections: FlowConnection[] = [
    {
      source_node_id: 'condition',
      target_node_id: 'a',
      condition: { field: 'approval_form.amount', operator: 'GT', value: 10000 },
    },
    { source_node_id: 'condition', target_node_id: 'b' },
    { source_node_id: 'condition', target_node_id: null },
  ]

  it('分支行带上序号、去向与拉线序号', () => {
    const model = buildCanvasModel([CONDITION, TARGET_A, TARGET_B], connections, {
      editable: true,
      fieldLabels: { 'approval_form.amount': '付款金额' },
    })
    const card = model.nodes[0]

    expect(card.isCondition).toBe(true)
    expect(card.showAddRow).toBe(true)
    expect(card.rows.map((row) => row.branch)).toEqual([0, 1, 2])
    expect(card.rows[0].text).toBe('付款金额 > 10000')
    // 中间那条没配条件要显出来，只有最后一条才是「其余情况」
    expect(card.rows[1].text).toBe('未配条件')
    expect(card.rows[1].problem).toBe('这条分支还没有配条件')
    expect(card.rows[2].isLast).toBe(true)
    expect(card.rows[2].text).toBe('其余情况')
    expect(card.rows[2].targetName).toBe('未接去向')
    expect(card.rows[2].linked).toBe(false)
  })

  it('只读版本不渲染「新增分支」行', () => {
    const model = buildCanvasModel([CONDITION], [], { editable: false })
    expect(model.nodes[0].showAddRow).toBe(false)
  })

  it('没有目标的连线不产生边', () => {
    const model = buildCanvasModel([CONDITION, TARGET_A, TARGET_B], connections, {
      editable: true,
      fieldLabels: { 'approval_form.amount': '付款金额' },
    })
    expect(model.edges).toHaveLength(2)
    expect(model.edges[0].kind).toBe('condition')
    expect(model.edges[0].label).toBe('付款金额 > 10000')
    expect(model.edges[0].actionTitle).toBe('断开这条分支的去向')
  })
})
