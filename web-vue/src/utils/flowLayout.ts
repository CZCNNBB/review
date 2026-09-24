import type { FlowConnection, FlowNode, Point } from '@/types/domain'

import { FLOW_NODE_HEIGHT, FLOW_NODE_WIDTH, FLOW_PADDING, nodeBox } from './flowGeometry'

/** 自动排版的横向/纵向间距。 */
const COLUMN_GAP = FLOW_NODE_WIDTH + 88
const ROW_GAP = FLOW_NODE_HEIGHT + 42

/**
 * 从开始节点做 BFS 分层，同层按出现顺序往下排。
 * 不可达的节点（没有从开始节点连过来）放到最后一层的后面，而不是原地不动。
 *
 * 与旧版的区别：**返回新数组**，不再就地改 position。就地改会让拖拽期的临时坐标
 * 与 store 里的数据打架，而且纯函数才能直接断言"坐标互不重复"。
 */
export function layoutNodes(nodes: FlowNode[], connections: FlowConnection[]): FlowNode[] {
  const known = new Set(nodes.map((node) => node.id))
  const outgoing = new Map<string, string[]>(nodes.map((node) => [node.id, []]))

  connections.forEach((connection) => {
    const list = outgoing.get(connection.source_node_id)
    if (list && connection.target_node_id && known.has(connection.target_node_id)) {
      list.push(connection.target_node_id)
    }
  })

  const layerOf = new Map<string, number>()
  const start = nodes.find((node) => node.node_type === 'START')

  if (start) {
    layerOf.set(start.id, 0)
    const queue = [start.id]
    while (queue.length) {
      const current = queue.shift() as string
      for (const next of outgoing.get(current) || []) {
        if (layerOf.has(next)) continue
        layerOf.set(next, (layerOf.get(current) as number) + 1)
        queue.push(next)
      }
    }
  }

  const maxLayer = Math.max(0, ...Array.from(layerOf.values()))
  nodes.forEach((node) => {
    if (!layerOf.has(node.id)) layerOf.set(node.id, maxLayer + 1)
  })

  const rowByLayer = new Map<number, number>()
  return nodes.map((node) => {
    const layer = layerOf.get(node.id) as number
    const row = rowByLayer.get(layer) || 0
    rowByLayer.set(layer, row + 1)

    return {
      ...node,
      position: {
        x: FLOW_PADDING + layer * COLUMN_GAP,
        y: FLOW_PADDING + row * ROW_GAP,
      },
    }
  })
}

/** 坐标缺失或重叠时提示用户点「自动排版」。 */
export function flowNeedsLayout(nodes: FlowNode[]): boolean {
  if (nodes.length < 2) return false

  const seen = new Set<string>()
  return nodes.some((node) => {
    const box = nodeBox(node)
    if (!box.x && !box.y) return true
    const key = `${box.x}:${box.y}`
    if (seen.has(key)) return true
    seen.add(key)
    return false
  })
}

/**
 * 新增节点的落点：摆到最右侧一列的右边，纵向错开三行。
 * 从面板拖入时用鼠标位置，点面板新增时用这个。
 */
export function defaultPositionFor(nodes: FlowNode[]): Point {
  const rightMost = nodes.reduce(
    (max, node) => Math.max(max, nodeBox(node).x),
    FLOW_PADDING - COLUMN_GAP,
  )
  return {
    x: rightMost + COLUMN_GAP,
    y: FLOW_PADDING + (nodes.length % 3) * ROW_GAP,
  }
}
