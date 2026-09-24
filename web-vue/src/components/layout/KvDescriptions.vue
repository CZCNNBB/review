<script setup lang="ts">
import {
  Descriptions as ADescriptions,
  DescriptionsItem as ADescriptionsItem,
} from 'ant-design-vue'

// 键值面板。旧版 kvHtml(pairs) 就是「标签 + 值」两列网格，交给 AntD Descriptions 表达；
// 观感由 styles/antd-theme.css 的 .kv-descriptions 对齐旧版 .kv（label 132px、次要色）。
//
// 值需要放链接、按钮这类富内容时用插槽：给这一项起个 slot 名，再在调用处写
// <template #slotName>…</template>。全库不用 v-html。
export interface KvPair {
  key: string
  value?: string
  /** 有插槽时忽略 value */
  slot?: string
  /** 鼠标悬停在标签上时显示：放原始字段名这类"要查得到但不该占视线"的技术细节 */
  hint?: string
}

defineProps<{
  pairs: Array<KvPair | null | undefined>
}>()
</script>

<template>
  <ADescriptions class="kv-descriptions" :column="1" :colon="false">
    <template v-for="pair in pairs" :key="(pair as KvPair).key">
      <ADescriptionsItem v-if="pair" :label="pair.hint ? undefined : pair.key">
        <template v-if="pair.hint" #label>
          <span :title="pair.hint">{{ pair.key }}</span>
        </template>
        <slot v-if="pair.slot" :name="pair.slot" />
        <span v-else>{{ pair.value }}</span>
      </ADescriptionsItem>
    </template>
  </ADescriptions>
</template>
