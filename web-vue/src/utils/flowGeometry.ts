import type { FlowConnection, FlowNode, Point, Size } from '@/types/domain'

export const FLOW_NODE_WIDTH = 184
export const FLOW_NODE_HEIGHT = 70
export const CONDITION_NODE_WIDTH = 232
/** 条件分支卡片：表头 + 每行分支 + 一行「＋ 新增分支」。 */
export const CONDITION_HEADER_HEIGHT = 42
export const CONDITION_ROW_HEIGHT = 28
export const FLOW_PADDING = 64

/** 节点在画布上的左上角坐标，缺省按 (0,0)。 */
export function nodeBox(node: Pick<FlowNode, 'position'>): Point {
  const position = node.position || { x: 0, y: 0 }
  return {
    x: typeof position.x === 'number' ? position.x : 0,
    y: typeof position.y === 'number' ? position.y : 0,
  }
}

/** 节点卡片配色变体。结束节点只有一种形态：流程走完、审批通过。 */
export function nodeVariant(node: Pick<FlowNode, 'node_type'>): string {
  if (node.node_type === 'START') return 'START'
  if (node.node_type === 'CONDITION') return 'CONDITION'
  if (node.node_type === 'END') return 'END-APPROVED'
  return 'APPROVAL'
}

export function nodeTypeLabel(node: Pick<FlowNode, 'node_type'>): string {
  if (node.node_type === 'START') return '开始'
  if (node.node_type === 'CONDITION') return '条件分支'
  if (node.node_type === 'END') return '结束'
  return '审批'
}

export interface EdgeGeometry {
  d: string
  mid: Point
  start: Point
  end: Point
}

export interface FlowGeometry {
  sizeOf(node: FlowNode): Size
  startOf(connection: FlowConnection): Point | null
  endOf(node: FlowNode): Point
  edgeOf(connection: FlowConnection): EdgeGeometry | null
  outgoingOf(nodeId: string): FlowConnection[]
  byId(id: string | null | undefined): FlowNode | undefined
}

/**
 * 节点尺寸、出口锚点与连线路径的唯一口径。
 * 渲染（节点卡片、SVG 路径）与交互（拖拽时重算连线）必须共用同一份结果，
 * 否则拖动时线会跳。
 *
 * `overrides` 是拖动中的临时坐标：拖动期间不动 nodes 数据，只把正在拖的那个节点
 * 的坐标放进来，这样重算一条线不必 clone 整份 nodes。
 */
export function createFlowGeometry(
  nodes: FlowNode[],
  connections: FlowConnection[],
  overrides?: Map<string, Point>,
): FlowGeometry {
  const nodeById = new Map(nodes.map((node) => [node.id, node]))
  const outgoingBySource = new Map<string, FlowConnection[]>()
  connections.forEach((connection) => {
    const list = outgoingBySource.get(connection.source_node_id)
    if (list) list.push(connection)
    else outgoingBySource.set(connection.source_node_id, [connection])
  })

  const byId = (id: string | null | undefined): FlowNode | undefined =>
    id ? nodeById.get(id) : undefined

  const outgoingOf = (nodeId: string): FlowConnection[] => outgoingBySource.get(nodeId) || []

  const boxOf = (node: FlowNode): Point => overrides?.get(node.id) ?? nodeBox(node)

  function sizeOf(node: FlowNode | undefined): Size {
    if (!node || node.node_type !== 'CONDITION') {
      return { width: FLOW_NODE_WIDTH, height: FLOW_NODE_HEIGHT }
    }
    // 多一行「＋ 新增分支」
    const rows = Math.max(1, outgoingOf(node.id).length) + 1
    return {
      width: CONDITION_NODE_WIDTH,
      height: CONDITION_HEADER_HEIGHT + rows * CONDITION_ROW_HEIGHT,
    }
  }

  /** 条件分支的每条分支从自己那一行的出口出发；普通节点从右侧中点出发。 */
  function startOf(connection: FlowConnection): Point | null {
    const node = byId(connection.source_node_id)
    if (!node) return null

    const box = boxOf(node)
    const size = sizeOf(node)

    if (node.node_type === 'CONDITION') {
      const position = outgoingOf(node.id).indexOf(connection)
      return {
        x: box.x + size.width,
        y:
          box.y +
          CONDITION_HEADER_HEIGHT +
          position * CONDITION_ROW_HEIGHT +
          CONDITION_ROW_HEIGHT / 2,
      }
    }
    return { x: box.x + size.width, y: box.y + size.height / 2 }
  }

  function endOf(node: FlowNode): Point {
    const box = boxOf(node)
    return { x: box.x, y: box.y + sizeOf(node).height / 2 }
  }

  function edgeOf(connection: FlowConnection): EdgeGeometry | null {
    const start = startOf(connection)
    const target = byId(connection.target_node_id)
    if (!start || !target) return null

    const end = endOf(target)
    const handle = Math.max(48, Math.abs(end.x - start.x) * 0.45)

    return {
      d: `M ${start.x} ${start.y} C ${start.x + handle} ${start.y}, ${end.x - handle} ${end.y}, ${end.x} ${end.y}`,
      // 三次贝塞尔在 t=0.5 处正好落在两端中点，标签直接用这个位置
      mid: { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 },
      start,
      end,
    }
  }

  return { sizeOf, startOf, endOf, edgeOf, outgoingOf, byId }
}

/** 画布尺寸：内容外扩一圈内边距，并保底 980×520。 */
export function flowStageSize(nodes: FlowNode[], connections: FlowConnection[]): Size {
  const geometry = createFlowGeometry(nodes, connections)
  let right = 0
  let bottom = 0

  nodes.forEach((node) => {
    const box = nodeBox(node)
    const size = geometry.sizeOf(node)
    right = Math.max(right, box.x + size.width)
    bottom = Math.max(bottom, box.y + size.height)
  })

  return {
    width: Math.max(980, right + FLOW_PADDING),
    height: Math.max(520, bottom + FLOW_PADDING),
  }
}
