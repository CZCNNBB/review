import type { JSONSchema, NodeDefinition } from '@/types/domain'

import { endpoints } from '../endpoints'
import { api } from '../http'
import type { Process, ProcessGraph, ProcessVersion, ValidationResult } from '../types'

export interface ProcessInput {
  name: string
  description?: string | null
}

/** 保存整图的载荷，字段与后端 ProcessGraphSaveRequest 对应（revision 是乐观锁）。 */
export interface GraphSaveInput {
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
  orchestration: { connections: unknown[] }
  form_schema: JSONSchema
}

export const processApi = {
  processes: (limit = 200) => api.get<Process[]>(endpoints.processes(limit)),

  get: (id: string) => api.get<Process>(endpoints.process(id)),

  create: (input: ProcessInput) => api.post<Process>(endpoints.processes(1).split('?')[0], input),

  copy: (id: string) => api.post<Process>(endpoints.copyProcess(id)),

  disable: (id: string) => api.post<Process>(endpoints.disableProcess(id)),

  createDraft: (id: string) => api.post<ProcessVersion>(endpoints.processDraft(id)),

  versions: (id: string) => api.get<ProcessVersion[]>(endpoints.processVersions(id)),

  graph: (versionId: string) => api.get<ProcessGraph>(endpoints.versionGraph(versionId)),

  saveGraph: (versionId: string, input: GraphSaveInput) =>
    api.put<ProcessGraph>(endpoints.versionGraph(versionId), input),

  validate: (versionId: string) => api.post<ValidationResult>(endpoints.validateVersion(versionId)),

  publish: (versionId: string) => api.post<ProcessVersion>(endpoints.publishVersion(versionId)),

  // 节点定义只读：清单跟着后端代码走，启动时由后端同步进库，控制台不再改写
  nodeDefinitions: (limit = 100) => api.get<NodeDefinition[]>(endpoints.nodeDefinitions(limit)),
}
