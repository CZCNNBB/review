<script setup lang="ts">
import {
  Descriptions as ADescriptions,
  DescriptionsItem as ADescriptionsItem,
  Empty as AEmpty,
  Popconfirm as APopconfirm,
  Table as ATable,
  Tooltip as ATooltip,
} from 'ant-design-vue'
import { ElButton, ElDialog, ElInput, ElOption, ElSelect } from 'element-plus'
import { ref } from 'vue'

import PageHead from '@/components/layout/PageHead.vue'

// 两库共存基线页。这是阶段 0 的验收物，不是业务页面：
// 1) Element 的弹窗里放 AntD 的表格、Tooltip、Popconfirm —— 浮层层级必须正确
//    （Element 弹窗基数 2000，AntD 默认 zIndexPopupBase 1000，不调就会被压住）；
// 2) 两套主题都要落在这套纸白 + 靛青的令牌上，看不出换过框架。
const dialogVisible = ref(false)
const selectValue = ref('AND')

const rows = [
  { key: '1', name: '财务审批', mode: '全部同意', count: 2 },
  { key: '2', name: '总经理审批', mode: '任意一人同意', count: 1 },
]

const columns = [
  { title: '节点', dataIndex: 'name', key: 'name' },
  { title: '审批模式', dataIndex: 'mode', key: 'mode' },
  { title: '审批人', dataIndex: 'count', key: 'count' },
]
</script>

<template>
  <PageHead
    title="两库共存基线"
    note="用来确认 Element Plus 与 Ant Design Vue 在这套设计令牌下能共存：层级、圆角、描边、字号都不打架。"
  />

  <div class="panel">
    <div class="panel__head"><h3>展示件走 AntD</h3></div>
    <div class="panel__body">
      <ATable :columns="columns" :data-source="rows" :pagination="false" size="small" />

      <div style="margin-top: 16px">
        <ADescriptions bordered size="small" :column="2">
          <ADescriptionsItem label="版本">V3</ADescriptionsItem>
          <ADescriptionsItem label="修订号">7</ADescriptionsItem>
          <ADescriptionsItem label="状态">草稿</ADescriptionsItem>
          <ADescriptionsItem label="更新时间">2026-09-24 10:00</ADescriptionsItem>
        </ADescriptions>

        <div style="margin-top: 12px; display: flex; gap: 12px; align-items: center">
          <ATooltip title="这条提示必须能盖在下面的弹窗上面">
            <span>悬停看 Tooltip 层级</span>
          </ATooltip>
          <APopconfirm title="确认执行？">
            <a>Popconfirm</a>
          </APopconfirm>
        </div>
      </div>
    </div>
  </div>

  <div class="panel">
    <div class="panel__head"><h3>录入件走 Element Plus</h3></div>
    <div class="panel__body">
      <div style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap">
        <ElSelect v-model="selectValue" style="width: 160px">
          <ElOption value="AND" label="全部同意" />
          <ElOption value="OR" label="任意一人同意" />
        </ElSelect>
        <ElInput placeholder="普通输入框" style="width: 200px" />
        <ElButton type="primary" @click="dialogVisible = true">打开弹窗</ElButton>
      </div>

      <div style="margin-top: 16px">
        <AEmpty description="表格没有数据时长这样" />
      </div>
    </div>
  </div>

  <ElDialog v-model="dialogVisible" title="弹窗里混用两个库" width="720px" append-to-body>
    <ATable :columns="columns" :data-source="rows" :pagination="false" size="small" />
    <div style="margin-top: 12px; display: flex; gap: 12px">
      <ATooltip title="这一句必须可见">
        <span>弹窗内的 AntD Tooltip</span>
      </ATooltip>
      <ElSelect v-model="selectValue" style="width: 160px">
        <ElOption value="AND" label="全部同意" />
        <ElOption value="OR" label="任意一人同意" />
      </ElSelect>
    </div>
    <template #footer>
      <ElButton @click="dialogVisible = false">关闭</ElButton>
    </template>
  </ElDialog>
</template>
