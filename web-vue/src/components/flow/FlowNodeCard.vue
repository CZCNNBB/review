<script setup lang="ts">
import FlowConditionRows from './FlowConditionRows.vue'

import type { CanvasNodeVM } from '@/utils/flowCanvasModel'

// 一张节点卡片。条件分支的出口全在分支行上，卡片本体不挂出口圆点。
// 位移用 transform 而不是 left/top：拖动时不触发布局，且与命令式写法一致。
const props = defineProps<{
  model: CanvasNodeVM
  editable: boolean
  dragging?: boolean
}>()

const emit = defineEmits<{
  (event: 'edit'): void
  (event: 'delete'): void
}>()

function cardStyle(): Record<string, string> {
  const style: Record<string, string> = {
    transform: `translate3d(${props.model.box.x}px, ${props.model.box.y}px, 0)`,
  }
  if (props.model.isCondition) style.width = `${props.model.size.width}px`
  return style
}
</script>

<template>
  <div
    class="flow__node"
    :class="[`flow__node--${model.variant}`, { 'is-dragging': props.dragging }]"
    :data-id="model.node.id"
    :style="cardStyle()"
  >
    <div class="flow__node-head">
      <span class="flow__node-type">{{ model.typeLabel }}</span>
      <span class="flow__node-name">{{ model.node.name }}</span>
      <span v-if="model.warning" class="flow__node-warn">{{ model.warning }}</span>
    </div>

    <FlowConditionRows
      v-if="model.isCondition"
      :rows="model.rows"
      :show-add-row="model.showAddRow"
      :editable="props.editable"
      @edit="emit('edit')"
    />
    <div v-else class="flow__node-desc">{{ model.summary }}</div>

    <template v-if="props.editable && !model.isCondition">
      <div v-if="model.node.node_type !== 'START'" class="flow__port flow__port--in"></div>
      <div
        v-if="model.node.node_type !== 'END'"
        class="flow__port flow__port--out"
        data-out="1"
        title="从这里拉一条线到下一个节点"
      ></div>
    </template>

    <div v-if="props.editable" class="flow__node-tools">
      <button type="button" @click.stop="emit('edit')">
        {{ model.isCondition ? '改名' : '配置' }}
      </button>
      <button
        v-if="model.node.node_type !== 'START'"
        class="is-danger"
        type="button"
        @click.stop="emit('delete')"
      >
        删除
      </button>
    </div>
  </div>
</template>
