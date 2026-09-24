import type { FlowConnection, FlowNode, JSONSchema } from '@/types/domain'

import { parseJsonInput } from './json'

/** 保存草稿要提交的整图载荷。字段与后端 ProcessGraphSaveRequest 对应。 */
export interface GraphPayload {
  revision: number
  name: string
  description: string | null
  nodes: Array<{
    id: string
    node_definition_id: string
    name: string
    config: Record<string, unknown>
    position: { x: number; y: number }
  }>
  orchestration: { connections: FlowConnection[] }
  form_schema: JSONSchema
}

export interface GraphEditorState {
  revision: number
  name: string
  description?: string | null
  formSchema: JSONSchema
  nodes: FlowNode[]
  connections: FlowConnection[]
}

/**
 * 审批表单 Schema 的权威来源在高级模式的文本框里 —— 用户在那里手改过 JSON 就得以它为准。
 * 文本为空或非法时抛错，把保存挡下来（旧版就是这个行为，只是当时从 DOM 里读）。
 */
export function resolveFormSchema(
  current: JSONSchema,
  rawSchemaText: string | null | undefined,
): JSONSchema {
  if (rawSchemaText === null || rawSchemaText === undefined) return current
  return parseJsonInput(rawSchemaText, '审批表单 Schema') as JSONSchema
}

/**
 * 组装保存载荷。
 * 契约②：`revision` 必须原样回传，后端靠它做乐观锁；少了它多人编辑会互相覆盖。
 */
export function collectPayload(state: GraphEditorState): GraphPayload {
  return {
    revision: state.revision,
    name: state.name,
    description: state.description || null,
    nodes: state.nodes.map((node) => ({
      id: node.id,
      node_definition_id: node.node_definition_id,
      name: node.name,
      config: node.config,
      position: node.position,
    })),
    orchestration: { connections: state.connections.map((item) => ({ ...item })) },
    form_schema: state.formSchema,
  }
}

/** 「编排数据」页签里展示的将提交内容。 */
export function buildRawPreview(state: GraphEditorState): unknown {
  const payload = collectPayload(state)
  return {
    revision: payload.revision,
    nodes: payload.nodes,
    orchestration: payload.orchestration,
  }
}

/** 「生成调用示例」里的 curl 命令。 */
export function buildCurl(
  base: string,
  processId: string,
  payload: unknown,
  apiKey: string,
): string {
  const normalized = base.replace(/\/+$/, '')
  const key = apiKey || '你的租户APIKey'
  return [
    `curl -X POST "${normalized}/api/processes/${processId}/instances" \\`,
    `  -H "X-API-Key: ${key}" \\`,
    '  -H "Content-Type: application/json" \\',
    `  -d '${JSON.stringify(payload, null, 2)}'`,
  ].join('\n')
}
