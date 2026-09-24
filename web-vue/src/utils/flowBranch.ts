import type { Condition, FlowConnection, FlowNode } from '@/types/domain'

import { NO_VALUE_OPERATORS, typedConditionValue } from './condition'
import type { FormFieldRow } from './schemaForm'

/** 分支编辑器里的一行草稿。弹窗关掉就丢，不进 store。 */
export interface BranchDraft {
  target_node_id: string | null
  condition: Condition | null
}

/** 拖动手势的判定阈值：位移不超过 2px 视为点击（契约⑤）。 */
export const DRAG_THRESHOLD = 2

export function isDragGesture(dx: number, dy: number): boolean {
  return Math.abs(dx) > DRAG_THRESHOLD || Math.abs(dy) > DRAG_THRESHOLD
}

/**
 * 分支行的阶梯规则：前面每条都要有条件，最后一条是「其余情况」不能带条件。
 * 返回 problem 用于卡片标黄与提示文案。
 */
export function branchRowState(
  connection: FlowConnection,
  nodes: FlowNode[],
  connections: FlowConnection[],
): { isLast: boolean; problem: string | null } {
  const node = nodes.find((item) => item.id === connection.source_node_id)
  if (!node || node.node_type !== 'CONDITION') return { isLast: false, problem: null }

  const siblings = connections.filter((item) => item.source_node_id === node.id)
  const isLast = siblings.indexOf(connection) === siblings.length - 1

  if (isLast && connection.condition) {
    return { isLast, problem: '最后一条是「其余情况」，不能配条件' }
  }
  if (!isLast && !connection.condition) {
    return { isLast, problem: '这条分支还没有配条件' }
  }
  return { isLast, problem: null }
}

/**
 * 卡片上的提醒。条件分支看分支有没有配完、有没有接去向；普通节点看到底有几条去向。
 */
export function flowNodeWarning(
  node: FlowNode,
  nodes: FlowNode[],
  connections: FlowConnection[],
): string | null {
  const outgoing = connections.filter((item) => item.source_node_id === node.id)

  if (node.node_type === 'CONDITION') {
    if (!outgoing.length) return '还没有分支'
    if (outgoing.some((item) => !item.target_node_id)) return '分支未接去向'
    return outgoing.some((item) => branchRowState(item, nodes, connections).problem)
      ? '分支未配完'
      : null
  }

  if (node.node_type === 'END') return null
  if (!outgoing.length) return '还没有去向'
  if (outgoing.length > 1) return '只能有一条去向'
  if (outgoing.some((item) => item.condition)) return '去向不能带条件'
  return null
}

export function hasConnection(
  connections: FlowConnection[],
  sourceId: string,
  targetId: string,
): boolean {
  return connections.some(
    (item) => item.source_node_id === sourceId && item.target_node_id === targetId,
  )
}

/** 普通节点拉线的结果：要么连上，要么给一个能直接提示用户的原因。 */
export type PlainConnectResult = { ok: true } | { ok: false; reason: 'duplicate' | 'multi-out' }

/** 普通节点只能有一条出线，分流必须走条件分支节点（契约④）。 */
export function canConnectPlain(
  connections: FlowConnection[],
  sourceId: string,
  targetId: string,
): PlainConnectResult {
  if (hasConnection(connections, sourceId, targetId)) return { ok: false, reason: 'duplicate' }
  if (connections.some((item) => item.source_node_id === sourceId)) {
    return { ok: false, reason: 'multi-out' }
  }
  return { ok: true }
}

/**
 * 从条件分支某一行的圆点拉线：只改这条分支的去向，不改条件。
 * branch 为 'new' 时新开一条分支（条件待配），插在「其余情况」之前。
 * 返回 null 表示这次拖拽没有产生变化。
 */
export function connectBranchTo(
  connections: FlowConnection[],
  nodeId: string,
  branch: string | number,
  targetId: string,
): { created: boolean; needsCondition: boolean } | null {
  const siblings = connections.filter((item) => item.source_node_id === nodeId)

  if (branch === 'new') {
    const connection: FlowConnection = { source_node_id: nodeId, target_node_id: targetId }
    const last = siblings[siblings.length - 1]
    if (last) connections.splice(connections.indexOf(last), 0, connection)
    else connections.push(connection)
    // 只有插在「其余情况」之前的那条才需要配条件
    return { created: true, needsCondition: Boolean(last) }
  }

  const connection = siblings[Number(branch)]
  if (!connection || connection.target_node_id === targetId) return null
  connection.target_node_id = targetId
  return { created: false, needsCondition: false }
}

/**
 * 分支编辑器提交：把草稿阶梯变成真正的出线。
 *
 * 契约③：数组顺序就是运行时匹配顺序，**最后一条恒为「其余情况」，其 condition 必须为空**，
 * 前面每条必须有字段。取值的类型转换失败会返回 error 交给弹窗内联显示。
 */
export function buildBranchConditions(
  branches: BranchDraft[],
  fieldOf: (path: string) => FormFieldRow | null,
): { built: BranchDraft[] } | { error: string } {
  const missing = branches.findIndex(
    (branch, index) =>
      index < branches.length - 1 && (!branch.condition || !branch.condition.field),
  )
  if (missing >= 0) {
    return { error: `条件 ${missing + 1} 还没有配完，只有最后一条才是“其余情况”` }
  }

  const built: BranchDraft[] = []
  for (const [index, branch] of branches.entries()) {
    const isLast = index === branches.length - 1
    const target = branch.target_node_id || null

    if (isLast || !branch.condition) {
      built.push({ target_node_id: target, condition: null })
      continue
    }

    const condition: Condition = {
      field: branch.condition.field,
      operator: branch.condition.operator,
    }

    if (!NO_VALUE_OPERATORS.includes(branch.condition.operator)) {
      try {
        condition.value = typedConditionValue(
          fieldOf(branch.condition.field),
          branch.condition.operator,
          branch.condition.value,
        )
      } catch (err) {
        return { error: err instanceof Error ? err.message : String(err) }
      }
    }

    built.push({ target_node_id: target, condition })
  }

  return { built }
}

/**
 * 把分支编辑器的结果写回编排：这个节点的出线整体重建，其余节点的连线原样保留、顺序不变。
 */
export function applyBranchDialogResult(
  connections: FlowConnection[],
  nodeId: string,
  built: BranchDraft[],
): FlowConnection[] {
  const others = connections.filter((item) => item.source_node_id !== nodeId)
  const rebuilt: FlowConnection[] = built.map((branch) => {
    const connection: FlowConnection = {
      source_node_id: nodeId,
      target_node_id: branch.target_node_id,
    }
    if (branch.condition) connection.condition = branch.condition
    return connection
  })
  return [...others, ...rebuilt]
}

/** 新增分支的草稿：插在「其余情况」之前，字段默认取第一个可选项。 */
export function newBranchDraft(fieldOptions: Array<{ value: string }>): BranchDraft {
  return {
    target_node_id: null,
    condition: { field: fieldOptions[0]?.value || '', operator: 'EQ', value: '' },
  }
}
