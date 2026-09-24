import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import type { ProcessGraph } from '@/api/types'
import type { FlowConnection, FlowNode, JSONSchema, NodeDefinition } from '@/types/domain'
import { applyBranchDialogResult, type BranchDraft } from '@/utils/flowBranch'
import { layoutNodes } from '@/utils/flowLayout'
import { defaultConfigFor, pruneNodeConfig } from '@/utils/nodeConfigForm'
import { collectPayload, resolveFormSchema } from '@/utils/payload'
import { formFieldLabels } from '@/utils/schemaForm'

/**
 * 版本编辑器的工作副本。
 *
 * 为什么进 store（而不是 provide/inject 或组件内 ref）：
 * 契约①要求「离开路由就丢弃」，而这需要一个**路由守卫能引用的全局点**。
 * provide/inject 做不到 —— 提供者本身是路由组件，beforeEach 执行时它还没挂载。
 *
 * 弹窗的草稿状态不进这里：节点配置弹窗没提交的字段、分支编辑器的阶梯都留在组件内，
 * 否则关掉再打开会看到上一次的脏值。
 */
export type EditorTab = 'form' | 'raw'

export const useVersionEditorStore = defineStore('versionEditor', () => {
  const versionId = ref('')
  const processId = ref('')
  const versionNo = ref(0)
  const status = ref('')
  const revision = ref(0)
  const name = ref('')
  const description = ref<string | null>(null)
  const formSchema = ref<JSONSchema>({ type: 'object', properties: {} })
  /** 高级模式文本框里的原文：它是 Schema 的权威来源，保存时以它为准。 */
  const formSchemaText = ref('')
  const formAdvanced = ref(false)
  const nodes = ref<FlowNode[]>([])
  const connections = ref<FlowConnection[]>([])
  const dirty = ref(false)
  const activeTab = ref<EditorTab>('form')
  /** 画布缩放跨页签切换保留，但离开路由随工作副本一起丢。 */
  const flowScale = ref(1)
  const droppedConfigFields = ref<string[]>([])
  const loaded = ref(false)

  /** 契约⑦：只有草稿可编辑。画布、表单、工具栏共用这一个开关。 */
  const editable = computed(() => status.value === 'DRAFT')
  const fieldLabels = computed(() => formFieldLabels(formSchema.value))

  function loadFromGraph(graph: ProcessGraph, definitions: NodeDefinition[]): void {
    const definitionById = new Map(definitions.map((item) => [item.id, item]))
    const dropped: string[] = []

    versionId.value = graph.version_id
    processId.value = graph.process_id
    versionNo.value = graph.version_no
    status.value = graph.version_status
    revision.value = graph.revision
    name.value = graph.name
    description.value = graph.description
    formSchema.value = { ...(graph.form_schema || {}) }
    formSchemaText.value = JSON.stringify(formSchema.value, null, 2)
    formAdvanced.value = false
    activeTab.value = 'form'
    dirty.value = false

    nodes.value = graph.nodes.map((node) => {
      // 定义是配置项的唯一来源：定义里已删掉的键不再留着，否则保存会被校验拦下，
      // 而界面上根本没有地方去删它。
      const pruned = pruneNodeConfig(node, definitionById.get(node.node_definition_id))
      dropped.push(...pruned.dropped)
      return {
        id: node.id,
        node_definition_id: node.node_definition_id,
        node_type: node.node_type,
        node_definition_name: node.node_definition_name,
        name: node.name,
        config: pruned.config,
        position: { ...node.position },
      }
    })

    connections.value = (graph.orchestration?.connections || []).map((item) => ({ ...item }))
    droppedConfigFields.value = [...new Set(dropped)]
    loaded.value = true
  }

  /** 离开路由或保存成功后调用。 */
  function reset(): void {
    loaded.value = false
    versionId.value = ''
    nodes.value = []
    connections.value = []
    dirty.value = false
    droppedConfigFields.value = []
    flowScale.value = 1
    formAdvanced.value = false
    activeTab.value = 'form'
  }

  function markDirty(): void {
    dirty.value = true
  }

  function addNode(definition: NodeDefinition, config?: Record<string, unknown>): FlowNode {
    const node: FlowNode = {
      id: crypto.randomUUID(),
      node_definition_id: definition.id,
      node_type: definition.node_type,
      node_definition_name: definition.name,
      name: definition.name,
      config: config ?? defaultConfigFor(definition),
      position: { x: 0, y: 0 },
    }
    nodes.value = [...nodes.value, node]
    markDirty()
    return node
  }

  function updateNode(nodeId: string, patch: Partial<FlowNode>): void {
    nodes.value = nodes.value.map((node) => (node.id === nodeId ? { ...node, ...patch } : node))
    markDirty()
  }

  function removeNode(nodeId: string): void {
    nodes.value = nodes.value.filter((node) => node.id !== nodeId)
    // 连带删掉挂在它身上的连线，否则会留下指向不存在节点的悬空边
    connections.value = connections.value.filter(
      (item) => item.source_node_id !== nodeId && item.target_node_id !== nodeId,
    )
    markDirty()
  }

  function setNodePosition(nodeId: string, position: { x: number; y: number }): void {
    nodes.value = nodes.value.map((node) => (node.id === nodeId ? { ...node, position } : node))
    markDirty()
  }

  function setConnections(next: FlowConnection[]): void {
    connections.value = next
    markDirty()
  }

  function autoLayout(): void {
    nodes.value = layoutNodes(nodes.value, connections.value)
    markDirty()
  }

  /** 分支编辑器保存：这个节点的出线整体重建，其余节点的连线原样保留（契约③）。 */
  function applyBranchResult(nodeId: string, built: BranchDraft[]): void {
    connections.value = applyBranchDialogResult(connections.value, nodeId, built)
    markDirty()
  }

  function setFormSchema(next: JSONSchema): void {
    formSchema.value = next
    formSchemaText.value = JSON.stringify(next, null, 2)
    markDirty()
  }

  /** 保存载荷（契约②：带 revision）。高级模式下文本框内容才是 Schema 的权威来源。 */
  function buildPayload(): ReturnType<typeof collectPayload> {
    return collectPayload({
      revision: revision.value,
      name: name.value,
      description: description.value,
      formSchema: resolveFormSchema(
        formSchema.value,
        formAdvanced.value ? formSchemaText.value : null,
      ),
      nodes: nodes.value,
      connections: connections.value,
    })
  }

  return {
    versionId,
    processId,
    versionNo,
    status,
    revision,
    name,
    description,
    formSchema,
    formSchemaText,
    formAdvanced,
    nodes,
    connections,
    dirty,
    activeTab,
    flowScale,
    droppedConfigFields,
    loaded,
    editable,
    fieldLabels,
    loadFromGraph,
    reset,
    markDirty,
    addNode,
    updateNode,
    removeNode,
    setNodePosition,
    setConnections,
    autoLayout,
    applyBranchResult,
    setFormSchema,
    buildPayload,
  }
})
