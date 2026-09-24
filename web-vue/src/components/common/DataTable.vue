<script lang="ts">
/**
 * 列定义。保持旧版 tableHtml(columns, rows, empty) 的三段式：给 key 与标题，
 * 单元格默认渲染 row[key]；想放标签、链接、按钮就写一个名为 `cell-<key>` 的插槽。
 * 旧版靠拼 HTML 字符串 + esc() 防 XSS，这里插槽返回的是 VNode，天然安全。
 *
 * 类型放在普通 <script> 里导出：<script setup> 的绑定不对外暴露，
 * 页面 import 不到 ColumnSpec。
 */
export interface ColumnSpec {
  key: string
  title: string
  width?: number
  align?: 'left' | 'right' | 'center'
}
</script>

<script setup lang="ts" generic="T extends object">
import { Table as ATable, type TableColumnsType } from 'ant-design-vue'
import { computed, useSlots } from 'vue'

import EmptyState from '@/components/layout/EmptyState.vue'

// 数据表。展示件统一走 AntD，页面里不再直接出现 <a-table>。
const props = defineProps<{
  columns: ColumnSpec[]
  rows: T[]
  rowKey?: string
  emptyTitle?: string
  emptyHint?: string
  loading?: boolean
}>()

const slots = useSlots()

// 动态插槽名要显式声明，否则父组件写 #cell-xxx 时 vue-tsc 会报「不认识这个插槽」。
defineSlots<{
  [key: `cell-${string}`]: (props: { row: T }) => unknown
  'empty-action'?: () => unknown
}>()

/**
 * key 叫 actions 的就是操作列：右对齐不换行，几个链接按钮排在一条线上。
 * 各页面的操作列本来就用这个 key，不必再在列定义里重复声明一次。
 * 对应旧版列定义上的 cls: 'is-actions' 与 `.tbl td.is-actions`。
 */
const isActionsColumn = (key: string): boolean => key === 'actions'

const antColumns = computed<TableColumnsType>(() =>
  props.columns.map((column) => ({
    title: column.title,
    dataIndex: column.key,
    key: column.key,
    width: column.width,
    align: column.align,
    customRender: ({ record }: { record: T }) => {
      const slot = slots[`cell-${column.key}`]
      if (slot) return slot({ row: record })
      const value = (record as Record<string, unknown>)[column.key]
      return value === null || value === undefined ? '—' : String(value)
    },
    customCell: isActionsColumn(column.key) ? () => ({ class: 'is-actions' }) : undefined,
  })),
)
</script>

<template>
  <ATable
    class="data-table"
    :columns="antColumns"
    :data-source="props.rows"
    :row-key="props.rowKey || 'id'"
    :loading="props.loading"
    :pagination="false"
    size="middle"
  >
    <template #emptyText>
      <EmptyState :title="props.emptyTitle || '暂无数据'" :hint="props.emptyHint">
        <slot name="empty-action" />
      </EmptyState>
    </template>
  </ATable>
</template>

<style scoped>
.data-table :deep(td) {
  vertical-align: middle;
}

/* 操作列：几个链接按钮排在一条线上，不换行，右对齐（旧版 .tbl td.is-actions 的同一套） */
.data-table :deep(td.is-actions) {
  white-space: nowrap;
  text-align: right;
}
</style>
