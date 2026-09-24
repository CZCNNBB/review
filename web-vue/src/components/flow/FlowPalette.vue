<script setup lang="ts">
import { computed } from 'vue'

import type { FlowNode, NodeDefinition } from '@/types/domain'
import { nodeTypeLabel, nodeVariant } from '@/utils/flowGeometry'
import { defaultConfigFor, nodeConfigSummary } from '@/utils/nodeConfigForm'

// 左侧节点面板：按执行类型分组，拖到画布上新增节点，点一下也能新增。
// 分组是**按接口返回的定义动态生成**的，以后加节点类型不用改这里。
const props = defineProps<{
  definitions: NodeDefinition[]
  nodes: FlowNode[]
  editable: boolean
}>()

const emit = defineEmits<{
  (event: 'add', definitionId: string): void
  (event: 'drag-start', definitionId: string): void
}>()

const usable = computed(() => props.definitions.filter((item) => item.status === 'ENABLED'))

/** 每个定义各自一个屏幕外的拖拽影像，setDragImage 时直接取，不用等 Vue 更新。 */
const ghosts = new Map<string, HTMLElement>()

function registerGhost(definitionId: string, element: HTMLElement | null): void {
  if (element) ghosts.set(definitionId, element)
  else ghosts.delete(definitionId)
}
const hasStart = computed(() => props.nodes.some((node) => node.node_type === 'START'))

/** 分组顺序按定义返回的顺序，同类型归一组。 */
const groups = computed(() => {
  const types: string[] = []
  usable.value.forEach((definition) => {
    if (!types.includes(definition.node_type)) types.push(definition.node_type)
  })
  return types.map((type) => ({
    type,
    label:
      usable.value.find((item) => item.node_type === type)?.name ||
      nodeTypeLabel({ node_type: type }),
    items: usable.value.filter((item) => item.node_type === type),
  }))
})

function blocked(definition: NodeDefinition): boolean {
  return definition.node_type === 'START' && hasStart.value
}

/** 拖拽影像用节点卡本身（所见即所得）。 */
function onDragStart(event: DragEvent, definition: NodeDefinition): void {
  const ghost = ghosts.get(definition.id)
  if (!ghost || !event.dataTransfer) return
  event.dataTransfer.setData('text/plain', definition.id)
  event.dataTransfer.effectAllowed = 'copy'
  event.dataTransfer.setDragImage(ghost, 26, 30)
  emit('drag-start', definition.id)
}

function previewOf(definition: NodeDefinition): { variant: string; summary: string } {
  const preview = {
    node_type: definition.node_type,
    config: defaultConfigFor(definition),
  }
  return { variant: nodeVariant(preview), summary: nodeConfigSummary(preview) }
}
</script>

<template>
  <div class="flow-palette">
    <template v-if="props.editable">
      <div class="flow-palette__title">拖到画布上新增节点</div>
      <template v-if="usable.length">
        <div v-for="group in groups" :key="group.type" class="flow-palette__group">
          {{ group.label }}
          <div
            v-for="definition in group.items"
            :key="definition.id"
            class="flow-palette__item"
            :class="{ 'is-disabled': blocked(definition) }"
            :draggable="!blocked(definition)"
            :title="
              blocked(definition) ? '每条流程只能有一个开始节点' : '拖到画布上，或点击直接新增'
            "
            @click="!blocked(definition) && emit('add', definition.id)"
            @dragstart="onDragStart($event, definition)"
          >
            <span
              class="flow-palette__dot"
              :class="`flow-palette__dot--${definition.node_type}`"
            ></span>
            {{ definition.name }}
          </div>
        </div>
      </template>
      <div v-else class="flow-palette__hint">
        没有可用的节点定义。先去「节点定义」页面创建，或执行 init.sql 带入种子定义。
      </div>
    </template>
    <div v-else class="flow-palette__hint">
      已发布版本只读，不能新增节点。需要修改请创建下一版草稿。
    </div>

    <!-- 拖拽影像：常驻在屏幕外。setDragImage 要求元素已在 DOM 中，
         而 Vue 的更新是异步的，所以不能等 dragstart 时再挂出来。 -->
    <div
      v-for="definition in usable"
      :key="`ghost-${definition.id}`"
      :ref="(el) => registerGhost(definition.id, el as HTMLElement | null)"
      class="flow__node flow__node--ghost"
      :class="`flow__node--${previewOf(definition).variant}`"
    >
      <div class="flow__node-head">
        <span class="flow__node-type">{{ definition.name }}</span>
        <span class="flow__node-name">{{ definition.name }}</span>
      </div>
      <div class="flow__node-desc">{{ previewOf(definition).summary }}</div>
    </div>
  </div>
</template>
