<script setup lang="ts">
import { computed, onMounted } from 'vue'

import { processApi } from '@/api/modules/process'
import CodeText from '@/components/common/CodeText.vue'
import DataTable from '@/components/common/DataTable.vue'
import type { ColumnSpec } from '@/components/common/DataTable.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import ErrorPanel from '@/components/layout/ErrorPanel.vue'
import PageHead from '@/components/layout/PageHead.vue'
import PanelCard from '@/components/layout/PanelCard.vue'
import { useAsyncPage } from '@/composables/useAsyncPage'
import { useShellStore } from '@/stores/shell'
import type { NodeDefinition } from '@/types/domain'

const columns: ColumnSpec[] = [
  { key: 'name', title: '名称', width: 180 },
  { key: 'node_type', title: '执行类型', width: 130 },
  { key: 'config', title: '配置项', width: 340 },
  { key: 'status', title: '状态', width: 90 },
  { key: 'description', title: '说明' },
]

const shell = useShellStore()

// 解构出来用：模板里 ref 会自动解包，不必到处写 .value
const {
  data: definitions,
  loading,
  error,
  refresh,
} = useAsyncPage(async () => {
  const list = await processApi.nodeDefinitions(100)
  shell.setCount('definitions', list.length)
  return list
}, [] as NodeDefinition[])

/** 配置项摘要：按 schema 里的顺序排开，必填的缀一个星号。 */
function configSummary(definition: NodeDefinition): Array<{ title: string; required: boolean }> {
  const schema = definition.config_schema_json || {}
  const properties = schema.properties || {}
  const required = new Set(schema.required || [])
  return Object.keys(properties).map((name) => ({
    title: (properties[name] || {}).title || name,
    required: required.has(name),
  }))
}

// 每行的配置项摘要在取数后算一次即可，不必让表格为每个单元格再算一遍
const rows = computed(() =>
  definitions.value.map((definition) => ({
    ...definition,
    config_items: configSummary(definition),
  })),
)

onMounted(refresh)
</script>

<template>
  <PageHead title="节点定义">
    <template #note>
      系统支持哪些节点由后端代码定义，应用启动时同步到这里，所以这个页面是只读的。<br />
      画布上能放哪些节点、每种节点允许配什么，都读这份清单；而“这条流程用谁审批、怎么审批”是在审批流里填的。<br />
      新增一种节点类型要后端实现（处理器 + 注册表 + 类型清单各加一处），不用在这里手工造。
    </template>
  </PageHead>

  <ErrorPanel v-if="error" :error="error" />

  <PanelCard v-else>
    <div class="note note--work definition-note">
      什么时候需要来这里：核对画布上能放哪些节点、每种节点允许配什么，或者排查某个能力为什么没出现。
      清单跟着后端代码走，改配置规则要改代码并重启。
      <strong>给已有定义加必填项，会让老草稿在下次保存时报错</strong>，所以补新能力时建议加成选填。
    </div>
    <DataTable
      :columns="columns"
      :rows="rows"
      :loading="loading"
      empty-title="还没有节点定义"
      empty-hint="全新库启动一次应用就会按代码清单写入；一直为空的话，看后端启动日志里的「节点定义同步失败」。"
    >
      <template #cell-name="{ row }">
        <span class="cell-title">{{ row.name }}</span>
      </template>
      <template #cell-node_type="{ row }">
        <CodeText :text="row.node_type" />
      </template>
      <template #cell-config="{ row }">
        <span v-if="row.config_items.length" class="config-tags">
          <span v-for="item in row.config_items" :key="item.title" class="tag">
            {{ item.title }}{{ item.required ? ' *' : '' }}
          </span>
        </span>
        <span v-else class="muted">无配置项</span>
      </template>
      <template #cell-status="{ row }">
        <StatusTag :status="row.status" />
      </template>
      <template #cell-description="{ row }">
        <span class="muted">{{ row.description || '—' }}</span>
      </template>
    </DataTable>
  </PanelCard>
</template>

<style scoped>
/* 表格上方的说明条与下面的表格之间留一点空 */
.definition-note {
  margin-bottom: 14px;
}
/* 旧版的 .muted / .cell-title 挂在 .tbl 下，AntD 表格里继承不到，按同一套令牌补一份 */
.muted {
  color: var(--ink-3);
}
.cell-title {
  font-weight: 600;
}
/* 配置项标签排一行，放不下就换行 */
.config-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
