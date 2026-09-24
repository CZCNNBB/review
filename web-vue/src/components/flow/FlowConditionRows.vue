<script setup lang="ts">
import type { ConditionRowVM } from '@/utils/flowCanvasModel'

// 条件分支卡片里的分支行：序号 + 条件 + 去向 + 自己那一行的出口圆点。
// 出口圆点带 data-branch，拉线时靠它知道「这次拉的是第几条分支」（契约③）。
// 点行本身打开分支编辑器 —— 注意判定顺序：圆点在行内部，命中判定必须先看圆点。
const props = defineProps<{
  rows: ConditionRowVM[]
  showAddRow: boolean
  editable: boolean
}>()

const emit = defineEmits<{
  (event: 'edit'): void
}>()
</script>

<template>
  <div class="flow__rows">
    <div
      v-for="row in props.rows"
      :key="row.branch"
      class="flow__row"
      :class="{ 'is-incomplete': Boolean(row.problem) }"
      :title="row.problem || (props.editable ? '点这里改条件' : '')"
      @click="props.editable && emit('edit')"
    >
      <span class="flow__row-mark">{{ row.mark }}</span>
      <span class="flow__row-text">{{ row.isLast ? '其余情况' : row.text }}</span>
      <span class="flow__row-target" :class="{ 'is-unlinked': !row.linked }">
        → {{ row.targetName }}
      </span>
      <span
        v-if="props.editable"
        class="flow__row-port"
        :data-branch="row.branch"
        title="从这里拉一条线到目标节点"
      ></span>
    </div>

    <div
      v-if="props.showAddRow"
      class="flow__row flow__row--add"
      title="新增一条分支"
      @click="emit('edit')"
    >
      <span class="flow__row-text">＋ 新增分支</span>
      <span
        class="flow__row-port flow__row-port--add"
        data-branch="new"
        title="从这里拉一条线，直接连到新分支的目标节点"
      ></span>
    </div>
  </div>
</template>
