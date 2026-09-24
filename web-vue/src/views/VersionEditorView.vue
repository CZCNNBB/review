<script setup lang="ts">
import { ElButton } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { processApi } from '@/api/modules/process'
import type { ProcessGraph } from '@/api/types'
import BranchDialog from '@/components/flow/BranchDialog.vue'
import FlowCanvas from '@/components/flow/FlowCanvas.vue'
import FlowPalette from '@/components/flow/FlowPalette.vue'
import NodeConfigDialog from '@/components/flow/NodeConfigDialog.vue'
import Breadcrumb from '@/components/layout/Breadcrumb.vue'
import ErrorPanel from '@/components/layout/ErrorPanel.vue'
import KvDescriptions from '@/components/layout/KvDescriptions.vue'
import PageHead from '@/components/layout/PageHead.vue'
import PanelCard from '@/components/layout/PanelCard.vue'
import FormFieldTable from '@/components/schema/FormFieldTable.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import IssuesDialog from '@/components/common/IssuesDialog.vue'
import JsonBlock from '@/components/common/JsonBlock.vue'
import CodeTextarea from '@/components/common/CodeTextarea.vue'
import { confirmAction, errorMessageOf } from '@/composables/useConfirm'
import { useAsyncPage } from '@/composables/useAsyncPage'
import { usePersonDirectory } from '@/composables/usePersonDirectory'
import { useVersionEditorStore } from '@/stores/versionEditor'
import type { FlowNode, NodeDefinition, ValidationIssue } from '@/types/domain'
import { canConnectPlain } from '@/utils/flowBranch'
import { defaultPositionFor, flowNeedsLayout } from '@/utils/flowLayout'
import { createFlowGeometry } from '@/utils/flowGeometry'
import { formatTime } from '@/utils/format'
import { toastError, toastOk } from '@/utils/notify'

const route = useRoute()
const router = useRouter()
const editor = useVersionEditorStore()

const versionId = computed(() => String(route.params.id || ''))
const canvasRef = ref<InstanceType<typeof FlowCanvas> | null>(null)

const graph = ref<ProcessGraph | null>(null)
const definitions = ref<NodeDefinition[]>([])
// 审批人候选：走人员目录拉（自带部门，选人下拉里缀成小标签）
const directory = usePersonDirectory()

const page = useAsyncPage(
  async () => {
    const [loadedGraph, loadedDefinitions] = await Promise.all([
      processApi.graph(versionId.value),
      processApi.nodeDefinitions(100),
    ])
    graph.value = loadedGraph
    definitions.value = loadedDefinitions

    // 工作副本：同一版本重复进入（切页签、开关弹窗）都复用，离开路由才丢
    if (editor.versionId !== loadedGraph.version_id) {
      editor.loadFromGraph(loadedGraph, loadedDefinitions)
      if (editor.droppedConfigFields.length) {
        toastOk(`已按节点定义忽略失效配置：${editor.droppedConfigFields.join('、')}`)
      }
    }
    return loadedGraph
  },
  null as ProcessGraph | null,
)

const personOptions = computed(() => directory.options.value)
const definitionById = (id: string): NodeDefinition | undefined =>
  definitions.value.find((item) => item.id === id)

const needsLayout = computed(() =>
  editor.loaded && !editor.editable ? false : flowNeedsLayout(editor.nodes),
)

/* ---------------------------------------------------------------------------
   弹窗：节点配置 / 条件分支 / 校验结果
   --------------------------------------------------------------------------- */

const nodeDialogOpen = ref(false)
const editingNode = ref<FlowNode | null>(null)
const editingIsNew = ref(false)

const branchDialogOpen = ref(false)
const branchNode = ref<FlowNode | null>(null)

const issuesOpen = ref(false)
const issuesTitle = ref('校验结果')
const issues = ref<ValidationIssue[]>([])

function openNodeDialog(node: FlowNode, isNew = false): void {
  editingNode.value = node
  editingIsNew.value = isNew
  nodeDialogOpen.value = true
}

function openBranchDialog(node: FlowNode): void {
  branchNode.value = node
  branchDialogOpen.value = true
}

function createNode(definitionId: string, position?: { x: number; y: number }): void {
  const definition = definitionById(definitionId)
  if (!definition) {
    toastError('节点定义不存在，请刷新页面')
    return
  }
  if (definition.node_type === 'START' && editor.nodes.some((node) => node.node_type === 'START')) {
    toastError('每条流程只能有一个开始节点')
    return
  }
  const node = editor.addNode(definition)
  // 点面板新增时没有光标位置，落到最右列的右边
  editor.setNodePosition(node.id, position || defaultPositionFor(editor.nodes))
  openNodeDialog(node, true)
}

function saveNode(payload: { name: string; config: Record<string, unknown> }): void {
  if (!editingNode.value) return
  editor.updateNode(editingNode.value.id, { name: payload.name, config: payload.config })
  editingNode.value = null
}

function saveBranch(built: Parameters<typeof editor.applyBranchResult>[1]): void {
  if (!branchNode.value) return
  editor.applyBranchResult(branchNode.value.id, built)
  branchNode.value = null
}

async function dropNode(nodeId: string): Promise<void> {
  const node = editor.nodes.find((item) => item.id === nodeId)
  if (!node) return
  const ok = await confirmAction({
    title: '删除节点',
    message: `删除节点「${node.name}」会同时删掉它相关的连线，确认删除？`,
    submitText: '删除',
    danger: true,
  })
  if (ok) editor.removeNode(nodeId)
}

/** 断开连线：普通线整条删掉，分支线只清去向（分支和条件留着）。 */
function dropConnection(index: number): void {
  const connection = editor.connections[index]
  if (!connection) return
  const source = editor.nodes.find((item) => item.id === connection.source_node_id)
  const next = [...editor.connections]

  if (source?.node_type === 'CONDITION') {
    next[index] = { ...connection, target_node_id: null }
    toastOk('已断开这条分支的去向，分支和条件还留着')
  } else {
    next.splice(index, 1)
    toastOk('已删除这条连线')
  }
  editor.setConnections(next)
}

function connect(payload: {
  sourceId: string
  targetId: string
  branch: string | number | null
}): void {
  const { sourceId, targetId, branch } = payload

  // 从分支行的圆点拉线：只改这条分支的去向
  if (branch !== null) {
    const siblings = editor.connections.filter((item) => item.source_node_id === sourceId)
    const next = [...editor.connections]

    if (branch === 'new') {
      const connection = { source_node_id: sourceId, target_node_id: targetId }
      const last = siblings[siblings.length - 1]
      if (last) next.splice(editor.connections.indexOf(last), 0, connection)
      else next.push(connection)
      editor.setConnections(next)
      // 新分支只要不是兜底那条，就得说明什么条件下走
      if (last) openBranchDialog(editor.nodes.find((item) => item.id === sourceId) as FlowNode)
      return
    }

    const connection = siblings[Number(branch)]
    if (!connection || connection.target_node_id === targetId) return
    next[editor.connections.indexOf(connection)] = { ...connection, target_node_id: targetId }
    editor.setConnections(next)
    return
  }

  // 普通节点的出口：契约④ —— 只能有一条出线，分流要走条件分支节点
  const result = canConnectPlain(editor.connections, sourceId, targetId)
  if (!result.ok) {
    toastError(
      result.reason === 'duplicate'
        ? '这两个节点已经连过了'
        : '普通节点只能有一条去向，要分流请加一个条件分支节点',
    )
    return
  }
  editor.setConnections([
    ...editor.connections,
    { source_node_id: sourceId, target_node_id: targetId },
  ])
}

function mergeNodeMove(payload: { nodeId: string; position: { x: number; y: number } }): void {
  editor.setNodePosition(payload.nodeId, payload.position)
}

/* ---------------------------------------------------------------------------
   保存 / 校验 / 发布
   --------------------------------------------------------------------------- */

const saving = ref(false)
const saveError = ref('')

async function save(): Promise<void> {
  saving.value = true
  saveError.value = ''
  try {
    const payload = editor.buildPayload()
    const saved = await processApi.saveGraph(versionId.value, payload)
    toastOk(`草稿已保存，修订号 ${saved.revision}`)
    editor.reset()
    await page.refresh()
  } catch (err) {
    saveError.value = errorMessageOf(err)
    toastError(saveError.value)
  } finally {
    saving.value = false
  }
}

async function validate(): Promise<void> {
  try {
    const result = await processApi.validate(versionId.value)
    if (result.valid) {
      toastOk('校验通过，可以发布')
      return
    }
    issuesTitle.value = '校验未通过'
    issues.value = result.issues
    issuesOpen.value = true
  } catch (err) {
    toastError(errorMessageOf(err))
  }
}

async function publish(): Promise<void> {
  const ok = await confirmAction({
    title: '发布版本',
    message: '发布会执行完整校验并把该版本切换为流程当前版本，已发布版本之后不可修改。确认发布？',
    submitText: '发布',
  })
  if (!ok) return
  try {
    await processApi.publish(versionId.value)
    toastOk('版本已发布')
    editor.reset()
    router.push(`/processes/${editor.processId || graph.value?.process_id}`)
  } catch (err) {
    toastError(errorMessageOf(err))
  }
}

/** 画布几何：给「自动排版」这类操作做参照，也用于调试。 */
const geometry = computed(() => createFlowGeometry(editor.nodes, editor.connections))

function autoLayout(): void {
  editor.autoLayout()
}

function setFormSchema(next: Parameters<typeof editor.setFormSchema>[0]): void {
  editor.setFormSchema(next)
}

onMounted(async () => {
  await page.refresh()
})

defineExpose({ geometry })
</script>

<template>
  <Breadcrumb
    :items="[
      { text: '审批流', hash: '#/processes' },
      { text: editor.name || graph?.name || '版本', hash: `#/processes/${graph?.process_id}` },
      { text: `V${editor.versionNo} 编排` },
    ]"
  />

  <ErrorPanel v-if="page.error.value" :error="page.error.value" />

  <template v-else-if="editor.loaded">
    <PageHead :title="`${editor.name} · V${editor.versionNo}`" :note="editor.description || ''">
      <StatusTag :status="editor.status" />
      <ElButton size="small" @click="validate">校验</ElButton>
      <ElButton v-if="editor.editable" size="small" :loading="saving" @click="save">
        保存草稿
      </ElButton>
      <ElButton v-if="editor.editable" size="small" type="primary" @click="publish">发布</ElButton>
    </PageHead>

    <PanelCard title="版本信息">
      <KvDescriptions
        :pairs="[
          { key: '版本 ID', value: editor.versionId },
          { key: '修订号', value: String(editor.revision) },
          { key: '更新时间', value: formatTime(graph?.updated_at) },
          {
            key: '发布时间',
            value: graph?.published_at ? formatTime(graph.published_at) : '未发布',
          },
        ]"
      />
    </PanelCard>

    <PanelCard title="流程画布">
      <template #actions>
        <span class="flow-bar">
          <ElButton v-if="editor.editable" size="small" @click="autoLayout">自动排版</ElButton>
          <span v-else class="panel__note">已发布版本只读，只能查看</span>
          <span v-if="editor.dirty" class="tag tag--wait">有未保存的改动</span>
          <span class="flow-bar__zoom">
            <button type="button" title="缩小" @click="canvasRef?.zoomBy(1 / 1.15)">−</button>
            <span>{{ canvasRef?.zoomPercent || '100%' }}</span>
            <button type="button" title="放大" @click="canvasRef?.zoomBy(1.15)">+</button>
            <button
              type="button"
              title="适应画布"
              style="width: auto; padding: 0 8px; font-size: 12px"
              @click="canvasRef?.zoomToFit()"
            >
              适应
            </button>
          </span>
        </span>
      </template>

      <div v-if="needsLayout" class="note note--work">
        有些节点还没有坐标或位置重叠，点「自动排版」把它们摆开。
      </div>

      <div class="flow-shell">
        <FlowPalette
          :definitions="definitions"
          :nodes="editor.nodes"
          :editable="editor.editable"
          @add="(definitionId) => createNode(definitionId)"
          @drag-start="(definitionId) => canvasRef?.startPaletteDrag(definitionId)"
        />

        <FlowCanvas
          ref="canvasRef"
          v-model:scale="editor.flowScale"
          :nodes="editor.nodes"
          :connections="editor.connections"
          :editable="editor.editable"
          :field-labels="editor.fieldLabels"
          @select="
            (nodeId) => openNodeDialog(editor.nodes.find((n) => n.id === nodeId) as FlowNode)
          "
          @edit="
            (nodeId) => {
              const node = editor.nodes.find((n) => n.id === nodeId) as FlowNode
              if (node.node_type === 'CONDITION') openBranchDialog(node)
              else openNodeDialog(node)
            }
          "
          @delete="dropNode"
          @drop-edge="dropConnection"
          @connect="connect"
          @move="mergeNodeMove"
          @create="(payload) => createNode(payload.definitionId, payload.position)"
        />
      </div>

      <div class="panel__body" style="padding-top: 12px">
        <div class="note">
          从左侧把节点拖到画布上新增，拖动节点摆位置，从节点右侧的圆点拖到另一个节点就连上了。
          <strong>普通节点只能有一条去向</strong>，需要分流就放一个「条件分支」节点：
          点它卡片上的分支行打开分支编辑器，前面每条写“如果……”，最后一条是“其余情况”兜底，
          每条分支自己有一个出口，线从那里引出。没配完的分支行会标黄。
          画布改动要点“保存草稿”才写入后端。
        </div>

        <div v-if="saveError" class="note note--wait">{{ saveError }}</div>
      </div>
    </PanelCard>

    <PanelCard title="审批表单与编排数据">
      <template #actions>
        <ElButton size="small" @click="editor.activeTab = 'form'">审批表单</ElButton>
        <ElButton size="small" @click="editor.activeTab = 'raw'">编排数据</ElButton>
        <ElButton size="small" @click="editor.formAdvanced = !editor.formAdvanced">
          {{ editor.formAdvanced ? '用字段表编辑' : '高级模式' }}
        </ElButton>
      </template>

      <template v-if="editor.activeTab === 'form'">
        <FormFieldTable
          v-if="!editor.formAdvanced"
          :schema="editor.formSchema"
          :readonly="!editor.editable"
          @update:schema="setFormSchema"
        />
        <template v-else>
          <div class="note">
            高级模式直接编辑 JSON
            Schema。切回字段表前会先试解析，含字段表表达不了的结构时会拒绝切换。
          </div>
          <CodeTextarea v-model="editor.formSchemaText" :readonly="!editor.editable" :rows="14" />
        </template>
      </template>

      <JsonBlock v-else :value="editor.buildPayload()" />
    </PanelCard>
  </template>

  <NodeConfigDialog
    v-if="editingNode"
    v-model:open="nodeDialogOpen"
    :node="editingNode"
    :definition="definitionById(editingNode.node_definition_id) as NodeDefinition"
    :person-options="personOptions"
    :is-new="editingIsNew"
    @save="saveNode"
    @goto-form="editor.activeTab = 'form'"
    @goto-branch="openBranchDialog(editingNode)"
  />

  <BranchDialog
    v-if="branchNode"
    v-model:open="branchDialogOpen"
    :node="branchNode"
    :nodes="editor.nodes"
    :connections="editor.connections"
    :form-schema="editor.formSchema"
    @save="saveBranch"
  />

  <IssuesDialog v-model:open="issuesOpen" :title="issuesTitle" :issues="issues" />
</template>
