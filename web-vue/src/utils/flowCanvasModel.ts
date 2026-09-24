import type { FlowConnection, FlowNode, Point, Size } from '@/types/domain'

import { conditionText } from './condition'
import { branchRowState, flowNodeWarning } from './flowBranch'
import {
  CONDITION_HEADER_HEIGHT,
  CONDITION_NODE_WIDTH,
  CONDITION_ROW_HEIGHT,
  createFlowGeometry,
  flowStageSize,
  nodeBox,
  nodeTypeLabel,
  nodeVariant,
} from './flowGeometry'
import { orderMark } from './format'
import { nodeConfigSummary } from './nodeConfigForm'

/** 条件分支卡片里的一行。 */
export interface ConditionRowVM {
  /** 该行在出线数组里的序号，拉线时回传给 connectBranchTo。 */
  branch: number
  mark: string
  text: string
  targetName: string
  linked: boolean
  problem: string | null
  isLast: boolean
}

export interface CanvasNodeVM {
  node: FlowNode
  box: Point
  size: Size
  variant: string
  typeLabel: string
  summary: string
  warning: string | null
  isCondition: boolean
  rows: ConditionRowVM[]
  /** 条件分支卡片末尾那一行「＋ 新增分支」 */
  showAddRow: boolean
}

export interface CanvasEdgeVM {
  index: number
  d: string
  mid: Point
  kind: 'plain' | 'condition'
  label: string
  /** 断开这条线的提示文案：普通线「删除这条连线」，分支线「断开这条分支的去向」 */
  actionTitle: string
}

export interface CanvasModel {
  stage: Size
  nodes: CanvasNodeVM[]
  edges: CanvasEdgeVM[]
}

function buildConditionRows(
  node: FlowNode,
  nodes: FlowNode[],
  connections: FlowConnection[],
  fieldLabels: Record<string, string>,
): ConditionRowVM[] {
  const outgoing = connections.filter((item) => item.source_node_id === node.id)

  return outgoing.map((connection, position) => {
    const state = branchRowState(connection, nodes, connections)
    const target = nodes.find((item) => item.id === connection.target_node_id)
    const linked = Boolean(connection.target_node_id)

    // 文字按位置判断：只有最后一行才是「其余情况」，中间的没配条件要显出来
    const text = state.isLast
      ? '其余情况'
      : connection.condition
        ? conditionText(connection.condition, fieldLabels)
        : '未配条件'

    return {
      branch: position,
      mark: state.isLast ? '—' : orderMark(position + 1),
      text,
      targetName: linked ? target?.name || '未知节点' : '未接去向',
      linked,
      problem: state.problem,
      isLast: state.isLast,
    }
  })
}

/**
 * 画布视图模型：把节点、连线与几何一次性算成模板直接可用的结构。
 *
 * 模板只遍历这个结果，不再有任何字符串拼 HTML —— 这也是"渲染与交互共用同一份几何"
 * 的落点：拖拽时 useFlowCanvas 用同一个 createFlowGeometry 只重算受影响的边。
 */
export function buildCanvasModel(
  nodes: FlowNode[],
  connections: FlowConnection[],
  options: { editable: boolean; fieldLabels?: Record<string, string> },
): CanvasModel {
  const fieldLabels = options.fieldLabels || {}
  const geometry = createFlowGeometry(nodes, connections)

  const nodeModels: CanvasNodeVM[] = nodes.map((node) => {
    const isCondition = node.node_type === 'CONDITION'
    const size = geometry.sizeOf(node)

    return {
      node,
      box: nodeBox(node),
      size,
      variant: nodeVariant(node),
      typeLabel: node.node_definition_name || nodeTypeLabel(node),
      summary: nodeConfigSummary(node),
      warning: flowNodeWarning(node, nodes, connections),
      isCondition,
      rows: isCondition ? buildConditionRows(node, nodes, connections, fieldLabels) : [],
      showAddRow: isCondition && options.editable,
    }
  })

  const edgeModels: CanvasEdgeVM[] = []
  connections.forEach((connection, index) => {
    const edge = geometry.edgeOf(connection)
    if (!edge) return

    const source = geometry.byId(connection.source_node_id)
    const isBranch = source?.node_type === 'CONDITION'

    edgeModels.push({
      index,
      d: edge.d,
      mid: edge.mid,
      kind: connection.condition ? 'condition' : 'plain',
      label: connection.condition ? conditionText(connection.condition, fieldLabels) : '',
      actionTitle: isBranch ? '断开这条分支的去向' : '删除这条连线',
    })
  })

  return { stage: flowStageSize(nodes, connections), nodes: nodeModels, edges: edgeModels }
}

/** 条件分支卡片的行几何：第 n 行的出口纵坐标。渲染与命中判定共用。 */
export function conditionRowY(box: Point, rowIndex: number): number {
  return (
    box.y + CONDITION_HEADER_HEIGHT + rowIndex * CONDITION_ROW_HEIGHT + CONDITION_ROW_HEIGHT / 2
  )
}

export { CONDITION_NODE_WIDTH }
