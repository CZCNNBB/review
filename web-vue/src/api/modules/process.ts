import type { JSONSchema, NodeDefinition } from '@/types/domain'

import { endpoints } from '../endpoints'
import { api } from '../http'
import type { Process, ProcessGraph, ProcessVersion, ValidationResult } from '../types'

export interface ProcessInput {
  name: string
  description?: string | null
}

export interface NodeDefinitionInput {
  node_type?: string
  name: string
  description?: string | null
  icon?: string | null
  config_schema_json: JSONSchema
  ui_schema_json: Record<string, unknown>
  status?: string
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

  nodeDefinitions: (limit = 100) => api.get<NodeDefinition[]>(endpoints.nodeDefinitions(limit)),

  createNodeDefinition: (input: NodeDefinitionInput) =>
    api.post<NodeDefinition>(endpoints.nodeDefinitions(1).split('?')[0], input),

  updateNodeDefinition: (id: string, input: Partial<NodeDefinitionInput>) =>
    api.patch<NodeDefinition>(endpoints.nodeDefinition(id), input),
}
