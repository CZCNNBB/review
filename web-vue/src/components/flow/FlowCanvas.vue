<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import FlowEdges from './FlowEdges.vue'
import FlowNodeCard from './FlowNodeCard.vue'

import type { FlowConnection, FlowNode, Point } from '@/types/domain'
import { useFlowCanvas } from '@/composables/useFlowCanvas'
import { buildCanvasModel } from '@/utils/flowCanvasModel'

// 画布根组件。交互全部交给 useFlowCanvas，这里只负责渲染与把回调转出去。
const props = defineProps<{
  nodes: FlowNode[]
  connections: FlowConnection[]
  editable: boolean
  fieldLabels: Record<string, string>
  scale: number
  selectedNodeId?: string | null
}>()

const emit = defineEmits<{
  (event: 'select', nodeId: string): void
  (
    event: 'connect',
    payload: { sourceId: string; targetId: string; branch: string | number | null },
  ): void
  (event: 'move', payload: { nodeId: string; position: Point }): void
  (event: 'create', payload: { definitionId: string; position: Point }): void
  (event: 'edit', nodeId: string): void
  (event: 'delete', nodeId: string): void
  (event: 'drop-edge', index: number): void
  (event: 'update:scale', scale: number): void
  (event: 'palette-drag', definitionId: string): void
}>()

const viewportRef = ref<HTMLElement | null>(null)
const stageRef = ref<HTMLElement | null>(null)

const scaleRef = computed({
  get: () => props.scale,
  set: (value: number) => emit('update:scale', value),
})

const canvas = useFlowCanvas({
  viewportRef,
  stageRef,
  nodes: () => props.nodes,
  connections: () => props.connections,
  editable: () => props.editable,
  scale: scaleRef,
  callbacks: {
    onSelectNode: (nodeId) => emit('select', nodeId),
    onConnect: (sourceId, targetId, branch) => emit('connect', { sourceId, targetId, branch }),
    onMoveNode: (nodeId, position) => emit('move', { nodeId, position }),
    onCreateNode: (definitionId, position) => emit('create', { definitionId, position }),
    onEditNode: (nodeId) => emit('edit', nodeId),
  },
})

const model = computed(() =>
  buildCanvasModel(props.nodes, props.connections, {
    editable: props.editable,
    fieldLabels: props.fieldLabels,
  }),
)

/** 缩放百分比：工具条与「适应」按钮都读它。 */
const zoomPercent = computed(() => `${Math.round(props.scale * 100)}%`)

function zoomBy(factor: number): void {
  canvas.applyScale(props.scale * factor)
}

/** 「适应」：把整张图缩到可视区内，并回到左上角。 */
function zoomToFit(): void {
  const container = viewportRef.value
  if (!container) return
  const fit = Math.min(
    1,
    (container.clientWidth - 32) / model.value.stage.width,
    (container.clientHeight - 32) / model.value.stage.height,
  )
  canvas.applyScale(fit)
  container.scrollTo({ left: 0, top: 0 })
}

onMounted(canvas.attach)

defineExpose({ startPaletteDrag: canvas.startPaletteDrag, zoomPercent, zoomBy, zoomToFit })
</script>

<template>
  <div ref="viewportRef" class="flow" :class="{ 'is-readonly': !props.editable }">
    <div
      class="flow__sizer"
      :style="{
        width: `${model.stage.width * props.scale}px`,
        height: `${model.stage.height * props.scale}px`,
      }"
    >
      <div
        ref="stageRef"
        class="flow__stage"
        :style="{
          width: `${model.stage.width}px`,
          height: `${model.stage.height}px`,
          transform: `scale(${props.scale})`,
        }"
      >
        <FlowEdges
          :edges="model.edges"
          :width="model.stage.width"
          :height="model.stage.height"
          :temp-edge="canvas.tempEdge.value"
        />

        <FlowNodeCard
          v-for="item in model.nodes"
          :key="item.node.id"
          :model="item"
          :editable="props.editable"
          :dragging="canvas.draggingNodeId.value === item.node.id"
          :class="{ 'is-selected': item.node.id === props.selectedNodeId }"
          @edit="emit('edit', item.node.id)"
          @delete="emit('delete', item.node.id)"
        />

        <!-- 线中点的条件摘要与断开按钮：位置由几何算出，拖拽时由 useFlowCanvas 直接改 style -->
        <div
          v-for="edge in model.edges"
          :key="`tools-${edge.index}`"
          class="flow__edge-tools"
          :data-conn="edge.index"
          :style="{ left: `${edge.mid.x}px`, top: `${edge.mid.y}px` }"
        >
          <span v-if="edge.label" class="flow__edge-label flow__edge-label--condition">
            {{ edge.label }}
          </span>
          <button
            v-if="props.editable"
            class="flow__edge-del"
            type="button"
            :title="edge.actionTitle"
            :aria-label="edge.actionTitle"
            @click="emit('drop-edge', edge.index)"
          >
            ×
          </button>
        </div>

        <div v-if="!model.nodes.length" class="flow__empty">
          <div>这条流程还没有节点</div>
          <div>从左边把节点拖进来开始编排。</div>
        </div>

        <!-- 面板拖入时的落点虚线框 -->
        <div
          v-if="canvas.dropHint.value"
          class="flow__drop-hint"
          :style="{ left: `${canvas.dropHint.value.x}px`, top: `${canvas.dropHint.value.y}px` }"
        ></div>
      </div>
    </div>
  </div>
</template>
