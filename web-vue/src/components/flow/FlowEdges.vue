<script setup lang="ts">
import type { CanvasEdgeVM } from '@/utils/flowCanvasModel'

// 连线层。分两层 path：可见的线 + 加粗的透明「命中层」（细线不好点中）。
// 线中点的条件摘要与断开按钮是 HTML 元素，由 FlowCanvas 摆位 —— 旧版就是这么做的，
// SVG 的 foreignObject 在各浏览器上表现不一致，不值得为它冒险。
defineProps<{
  edges: CanvasEdgeVM[]
  width: number
  height: number
  /** 拉线过程中的临时线，直接给 path 的 d */
  tempEdge: string | null
}>()
</script>

<template>
  <svg class="flow__edges" :width="width" :height="height">
    <defs>
      <marker
        id="flow-arrow"
        viewBox="0 0 10 10"
        refX="9"
        refY="5"
        markerWidth="7"
        markerHeight="7"
        orient="auto-start-reverse"
      >
        <path d="M 0 1 L 10 5 L 0 9 z" fill="#7c8894" />
      </marker>
      <marker
        id="flow-arrow-condition"
        viewBox="0 0 10 10"
        refX="9"
        refY="5"
        markerWidth="7"
        markerHeight="7"
        orient="auto-start-reverse"
      >
        <path d="M 0 1 L 10 5 L 0 9 z" fill="#2c4a73" />
      </marker>
    </defs>

    <path
      v-for="edge in edges"
      :key="`line-${edge.index}`"
      class="flow__edge"
      :class="`flow__edge--${edge.kind}`"
      :data-conn="edge.index"
      :d="edge.d"
      :marker-end="edge.kind === 'condition' ? 'url(#flow-arrow-condition)' : 'url(#flow-arrow)'"
    />
    <path
      v-for="edge in edges"
      :key="`hit-${edge.index}`"
      class="flow__edge-hit"
      :data-conn="edge.index"
      :d="edge.d"
    />

    <path
      v-if="tempEdge"
      class="flow__edge flow__edge--condition"
      :d="tempEdge"
      marker-end="url(#flow-arrow-condition)"
    />
  </svg>
</template>
