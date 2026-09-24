<script setup lang="ts">
import { ElButton } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import { processApi } from '@/api/modules/process'
import DataTable from '@/components/common/DataTable.vue'
import type { ColumnSpec } from '@/components/common/DataTable.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import NodeDefinitionDialog, { nodeTypeLabel } from '@/components/dialogs/NodeDefinitionDialog.vue'
import ErrorPanel from '@/components/layout/ErrorPanel.vue'
import PageHead from '@/components/layout/PageHead.vue'
import PanelCard from '@/components/layout/PanelCard.vue'
import { useAsyncPage } from '@/composables/useAsyncPage'
import { useShellStore } from '@/stores/shell'
import type { NodeDefinition } from '@/types/domain'

const columns: ColumnSpec[] = [
  { key: 'name', title: '名称', width: 180 },
  { key: 'node_type', title: '执行类型', width: 110 },
  { key: 'config', title: '配置项', width: 340 },
  { key: 'status', title: '状态', width: 90 },
  { key: 'description', title: '说明' },
  { key: 'actions', title: '操作', width: 90, align: 'right' },
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

const dialogOpen = ref(false)
const editing = ref<NodeDefinition | null>(null)

function openCreate(): void {
  editing.value = null
  dialogOpen.value = true
}

function openEdit(definition: NodeDefinition): void {
  editing.value = definition
  dialogOpen.value = true
}

onMounted(refresh)
</script>

<template>
  <PageHead title="节点定义">
    <template #note>
      这是系统支持的节点能力清单，一般不需要日常维护。<br />
      画布上能放哪些节点由它决定；而“这条流程用谁审批、怎么审批”是在审批流里填的，这里只管“这类节点允许配什么”。<br />
      执行类型只有开始、人工审批、结束三种，因为后端只有三个执行器；要加第四种执行语义需要后端开发。<br />
      同一种类型可以建多张定义（比如“财务审批”和“总经理审批”各自带不同规矩），也可以只用一张通用的。
    </template>
    <ElButton @click="openCreate">新建节点定义</ElButton>
  </PageHead>

  <ErrorPanel v-if="error" :error="error" />

  <PanelCard v-else>
    <div class="note note--work definition-note">
      什么时候需要来这里：系统新增了节点能力（例如人工审批多了“按部门选人”），或者要把某个能力停用。
      改配置规则会影响所有还在编辑中的草稿——<strong>给已有定义加必填项，会让老草稿在下次保存时报错</strong>，所以补新能力时建议加成选填。
    </div>
    <DataTable
      :columns="columns"
      :rows="rows"
      :loading="loading"
      empty-title="还没有节点定义"
      empty-hint="全新库执行 init.sql 会带入开始、人工审批、结束三个种子定义。"
    >
      <template #cell-name="{ row }">
        <span class="cell-title">{{ row.name }}</span>
      </template>
      <template #cell-node_type="{ row }">
        <span class="tag">{{ nodeTypeLabel(row.node_type) }}</span>
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
      <template #cell-actions="{ row }">
        <button class="btn--link btn--sm" type="button" @click="openEdit(row)">编辑</button>
      </template>
      <template #empty-action>
        <ElButton type="primary" size="small" @click="openCreate">新建节点定义</ElButton>
      </template>
    </DataTable>
  </PanelCard>

  <NodeDefinitionDialog v-model:open="dialogOpen" :definition="editing" @saved="refresh" />
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
