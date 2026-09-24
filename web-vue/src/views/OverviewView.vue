<script setup lang="ts">
import { computed, onMounted } from 'vue'

import { safe } from '@/api/http'
import { actionApi } from '@/api/modules/action'
import { orgApi } from '@/api/modules/org'
import { processApi } from '@/api/modules/process'
import type { ExecutionRecord, ProcessUsageRecord } from '@/api/types'
import DataTable from '@/components/common/DataTable.vue'
import type { ColumnSpec } from '@/components/common/DataTable.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import ErrorPanel from '@/components/layout/ErrorPanel.vue'
import KvDescriptions from '@/components/layout/KvDescriptions.vue'
import PageHead from '@/components/layout/PageHead.vue'
import PanelCard from '@/components/layout/PanelCard.vue'
import { useAsyncPage } from '@/composables/useAsyncPage'
import { useCredentialsStore } from '@/stores/credentials'
import { useShellStore } from '@/stores/shell'
import { formatTime } from '@/utils/format'

/** 每一步统计哪份数据；null 表示没有可统计的对象（发起、处理待办是动作，不是数据）。 */
type StepCountKey = 'tenants' | 'persons' | 'published' | 'actions' | 'grants' | 'executions'

interface LoopStep {
  name: string
  desc: string
  href: string
  key: StepCountKey | null
}

/**
 * 闭环八步。标题、说明、目标地址与计数来源照抄旧版 CLOSED_LOOP_STEPS：
 * 顺序就是业务跑通的顺序，任何一步没有数据，这条链路就还没闭。
 */
const CLOSED_LOOP_STEPS: LoopStep[] = [
  {
    name: '创建租户并配置接入凭据',
    desc: '业务系统接入审批中心的第一步，回调地址决定审批通过后请求发往哪里。',
    href: '#/tenants',
    key: 'tenants',
  },
  {
    name: '维护人员与部门',
    desc: '审批人、发起人都来自全局人员，审批流配置时需要选择具体人员。',
    href: '#/people',
    key: 'persons',
  },
  {
    name: '创建并发布审批流',
    desc: '编辑节点、审批人与分支条件，发布后才能被业务系统发起。',
    href: '#/processes',
    key: 'published',
  },
  {
    name: '配置业务动作',
    desc: '审批通过后要调用的业务接口，包含相对路径、参数规则和超时。',
    href: '#/actions',
    key: 'actions',
  },
  {
    name: '授权租户使用流程与动作',
    desc: '租户只有被授权后才能用对应流程发起审批、触发对应业务动作；在租户详情页里配。',
    href: '#/tenants',
    key: 'grants',
  },
  {
    name: '发起审批',
    desc: '业务系统用 API Key 调用发起接口，审批中心按当前发布版本创建实例。',
    href: '#/start',
    key: null,
  },
  {
    name: '处理待办任务',
    desc: '审批人查看审批单与时间线，同意或拒绝，引擎按 AND / OR 规则推进。',
    href: '#/tasks',
    key: null,
  },
  {
    name: '核对业务执行结果',
    desc: '审批通过后由后台 Worker 调用业务系统，执行记录保存入参、响应和失败原因。',
    href: '#/executions',
    key: 'executions',
  },
]

type StepCounts = Record<StepCountKey, number | null>

/** 使用记录接口是租户维度的，概览要合并各租户的记录，得自己把租户名带上。 */
type UsageRow = ProcessUsageRecord & { tenant_name: string }

interface OverviewData {
  counts: StepCounts
  executions: ExecutionRecord[]
  usages: UsageRow[]
}

const EMPTY_COUNTS: StepCounts = {
  tenants: null,
  persons: null,
  published: null,
  actions: null,
  grants: null,
  executions: null,
}

const usageColumns: ColumnSpec[] = [
  { key: 'created_at', title: '发起时间', width: 140 },
  { key: 'tenant_name', title: '租户', width: 150 },
  { key: 'approval_title', title: '审批单' },
  { key: 'business_key', title: '业务单号', width: 170 },
  { key: 'approval_status', title: '状态', width: 90 },
  { key: 'current_node_name', title: '当前节点', width: 150 },
]

const failedColumns: ColumnSpec[] = [
  { key: 'action_code', title: '业务动作', width: 180 },
  { key: 'error_message', title: '失败原因' },
  { key: 'created_at', title: '时间', width: 140 },
  { key: 'actions', title: '操作', width: 80, align: 'right' },
]

const shell = useShellStore()
const credentials = useCredentialsStore()

const { data, loading, error, refresh } = useAsyncPage<OverviewData>(
  async () => {
    // 聚合页的容错策略与旧版一致：五个列表各自 safe() 兜底，一个接口失败只让对应那块空着。
    // 概览要回答的是「哪一步还没做」，为一个接口把整页变成错误面板，反而丢掉了其余几块的有效信息。
    const [tenants, persons, processes, businessActions, executions] = await Promise.all([
      safe(credentials.loadTenants(), []),
      safe(orgApi.persons(200), []),
      safe(processApi.processes(200), []),
      safe(actionApi.list(200), []),
      safe(actionApi.executionRecords({ limit: 200 }), []),
    ])

    // 使用记录只有租户维度：扇出到每个租户再合并，才看得到全局的最近记录。
    const usageGroups = await Promise.all(
      tenants.map((tenant) => credentials.tenantUsageRecords(tenant.id)),
    )
    const usages: UsageRow[] = usageGroups
      .flatMap((list, index) =>
        list.map((record) => ({ ...record, tenant_name: tenants[index].name })),
      )
      .sort(
        (left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
      )

    const counts: StepCounts = {
      tenants: tenants.length,
      persons: persons.length,
      published: processes.filter((item) => item.current_version_id).length,
      actions: businessActions.length,
      // 授权是租户维度的数据，概览页不拉取（旧版同样留空），那一步只显示「进入」。
      grants: null,
      executions: executions.length,
    }

    // 概览是唯一一次性拿到这几份计数的页面，顺手把左侧导航的徽标一起写上。
    // 旧版这里写的是 persons，而导航 key 是 people，那个徽标从来没亮过 —— 这里按导航 key 写。
    shell.setCounts({
      tenants: counts.tenants ?? 0,
      people: counts.persons ?? 0,
      processes: processes.length,
      actions: counts.actions ?? 0,
      executions: counts.executions ?? 0,
    })
    // 闭环进度自己的徽标：八步里已经有数据的那几步。
    shell.setCount(
      'overview',
      CLOSED_LOOP_STEPS.filter((step) => step.key && (counts[step.key] ?? 0) > 0).length,
    )

    return { counts, executions, usages }
  },
  { counts: EMPTY_COUNTS, executions: [], usages: [] },
)

// 序号补成 01 这种两位，计数在这一层拼好，模板里不再做判断。
const steps = computed(() =>
  CLOSED_LOOP_STEPS.map((step, index) => ({
    no: String(index + 1).padStart(2, '0'),
    name: step.name,
    desc: step.desc,
    href: step.href,
    count: step.key ? data.value.counts[step.key] : null,
  })),
)

const approvalStats = computed(() => {
  const usages = data.value.usages
  const count = (status: string) => usages.filter((item) => item.approval_status === status).length
  return {
    total: usages.length,
    running: count('RUNNING'),
    approved: count('APPROVED'),
    rejected: count('REJECTED'),
    latest: usages.slice(0, 5),
  }
})

const executionStats = computed(() => {
  const executions = data.value.executions
  const count = (status: string) => executions.filter((item) => item.status === status).length
  return {
    total: executions.length,
    succeeded: count('SUCCEEDED'),
    failed: count('FAILED'),
    waiting: count('PENDING') + count('RUNNING'),
    failedRows: executions.filter((item) => item.status === 'FAILED').slice(0, 5),
  }
})

const approvalPairs = [
  { key: '审批总数', slot: 'approval-total' },
  { key: '审批中', slot: 'approval-running' },
  { key: '已通过', slot: 'approval-approved' },
  { key: '已拒绝', slot: 'approval-rejected' },
]

const executionPairs = [
  { key: '执行记录总数', slot: 'execution-total' },
  { key: '调用成功', slot: 'execution-succeeded' },
  { key: '调用失败', slot: 'execution-failed' },
  { key: '等待执行', slot: 'execution-waiting' },
]

onMounted(refresh)
</script>

<template>
  <PageHead
    title="闭环进度"
    note="按业务闭环的顺序排列。每一项都可以直接进入对应页面处理；计数来自当前接口返回的数据。"
  >
    <a class="btn" href="#/start">发起审批</a>
    <a class="btn btn--primary" href="#/tasks">处理待办</a>
  </PageHead>

  <ErrorPanel v-if="error" :error="error" />

  <template v-else>
    <PanelCard title="先把这条链路走通">
      <template #actions>
        <span class="panel__note">只有整条链路在同一环境跑通，当前阶段才算闭环</span>
      </template>
      <div class="steps">
        <div v-for="step in steps" :key="step.name" class="step">
          <div class="step__no">{{ step.no }}</div>
          <div>
            <div class="step__name">{{ step.name }}</div>
            <div class="step__desc">{{ step.desc }}</div>
          </div>
          <div class="step__side">
            <!-- 有计数的步骤才显示标签：>0 是「n 项」的绿色，0 是「未开始」的等待色 -->
            <StatusTag
              v-if="step.count !== null"
              :status="step.count > 0 ? 'ENABLED' : 'DRAFT'"
              :text="step.count > 0 ? `${step.count} 项` : '未开始'"
            />
            <a class="btn btn--sm" :href="step.href">进入</a>
          </div>
        </div>
      </div>
    </PanelCard>

    <PanelCard title="审批运行总览">
      <template #actions>
        <a class="btn btn--sm" href="#/usages">查看全部使用记录</a>
      </template>
      <KvDescriptions :pairs="approvalPairs">
        <template #approval-total>
          <span class="code">{{ approvalStats.total }}</span>
        </template>
        <template #approval-running>
          <span class="code count--indigo">{{ approvalStats.running }}</span>
        </template>
        <template #approval-approved>
          <span class="code count--pine">{{ approvalStats.approved }}</span>
        </template>
        <template #approval-rejected>
          <span class="code count--cinnabar">{{ approvalStats.rejected }}</span>
        </template>
      </KvDescriptions>
      <DataTable
        class="block"
        :columns="usageColumns"
        :rows="approvalStats.latest"
        :loading="loading"
        empty-title="还没有审批记录"
        empty-hint="业务系统发起审批后，这里会显示最近的处理情况。"
      >
        <template #cell-created_at="{ row }">
          <span class="muted">{{ formatTime(row.created_at) }}</span>
        </template>
        <template #cell-approval_title="{ row }">
          <a class="cell-title" :href="`#/instances/${row.approval_instance_id}`">
            {{ row.approval_title || '—' }}
          </a>
        </template>
        <template #cell-business_key="{ row }">
          <span class="code">{{ row.business_key }}</span>
        </template>
        <template #cell-approval_status="{ row }">
          <StatusTag :status="row.approval_status || 'ERROR'" />
        </template>
      </DataTable>
    </PanelCard>

    <PanelCard title="业务执行概况">
      <template #actions>
        <a class="btn btn--sm" href="#/executions">查看全部执行记录</a>
      </template>
      <KvDescriptions :pairs="executionPairs">
        <template #execution-total>
          <span class="code">{{ executionStats.total }}</span>
        </template>
        <template #execution-succeeded>
          <span class="code">{{ executionStats.succeeded }}</span>
        </template>
        <template #execution-failed>
          <!-- 有失败才染朱砂色：0 是常态，不该和异常一样扎眼 -->
          <span class="code" :class="{ 'count--cinnabar': executionStats.failed > 0 }">
            {{ executionStats.failed }}
          </span>
        </template>
        <template #execution-waiting>
          <span class="code">{{ executionStats.waiting }}</span>
        </template>
      </KvDescriptions>
      <div v-if="executionStats.failedRows.length" class="fail-block">
        <div class="fail-block__head">
          <h3 class="panel__title">最近失败的调用</h3>
          <span class="panel__note">第一版不自动重试，需要人工核对后处理</span>
        </div>
        <DataTable
          :columns="failedColumns"
          :rows="executionStats.failedRows"
          empty-title="暂无失败调用"
        >
          <template #cell-action_code="{ row }">
            <span class="code">{{ row.action_code }}</span>
          </template>
          <template #cell-error_message="{ row }">
            <span class="reason">{{ (row.error_message || '').slice(0, 80) }}</span>
          </template>
          <template #cell-created_at="{ row }">
            <span class="muted">{{ formatTime(row.created_at) }}</span>
          </template>
          <template #cell-actions="{ row }">
            <a class="btn--link btn--sm" :href="`#/executions/${row.id}`">查看</a>
          </template>
        </DataTable>
      </div>
    </PanelCard>
  </template>
</template>

<style scoped>
/* PanelCard 的 body 自带 16px 内边距，而步骤行自己就有 13px/16px 的内边距与通栏分隔线，
   这里把外层内边距抵消掉，保持旧版那种通栏的行分隔。 */
.steps {
  margin: -16px;
}

/* 键值面板与下面的表格之间留一口气 */
.block {
  display: block;
  margin-top: 16px;
}

.count--indigo {
  color: var(--indigo);
}
.count--pine {
  color: var(--pine);
}
.count--cinnabar {
  color: var(--cinnabar);
}
.muted {
  color: var(--ink-3);
}
.reason {
  color: var(--cinnabar);
}
/* 旧版的 .cell-title 只写在 .tbl 作用域里，AntD 的表格里匹配不到，这里补一条 */
.cell-title {
  font-weight: 600;
}

/* 面板内的次级小节头：失败列表要跟上面的统计分开，但仍是同一个面板 */
.fail-block {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--rule-weak);
}
.fail-block__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
</style>
