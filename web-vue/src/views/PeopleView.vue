<script setup lang="ts">
import { TabPane as ATabPane, Tabs as ATabs } from 'ant-design-vue'
import { ElButton, ElOption, ElSelect } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'

import { safe } from '@/api/http'
import { orgApi } from '@/api/modules/org'
import { tenantApi } from '@/api/modules/tenant'
import type { Department, Person, Tenant, TenantPersonBinding } from '@/api/types'
import CopyButton from '@/components/common/CopyButton.vue'
import DataTable from '@/components/common/DataTable.vue'
import type { ColumnSpec } from '@/components/common/DataTable.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import DepartmentFormDialog from '@/components/dialogs/DepartmentFormDialog.vue'
import DepartmentMembersDialog from '@/components/dialogs/DepartmentMembersDialog.vue'
import PersonFormDialog from '@/components/dialogs/PersonFormDialog.vue'
import TenantPersonBindDialog from '@/components/dialogs/TenantPersonBindDialog.vue'
import ErrorPanel from '@/components/layout/ErrorPanel.vue'
import PageHead from '@/components/layout/PageHead.vue'
import PanelCard from '@/components/layout/PanelCard.vue'
import { useAsyncPage } from '@/composables/useAsyncPage'
import { errorMessageOf } from '@/composables/useConfirm'
import { useUrlFilters } from '@/composables/useUrlFilters'
import { useShellStore } from '@/stores/shell'
import { formatTime } from '@/utils/format'
import { toastError, toastOk } from '@/utils/notify'

const personColumns: ColumnSpec[] = [
  { key: 'name', title: '姓名', width: 140 },
  { key: 'mobile', title: '手机号', width: 140 },
  { key: 'email', title: '邮箱' },
  { key: 'status', title: '状态', width: 90 },
  { key: 'id', title: '人员 ID', width: 220 },
  { key: 'actions', title: '操作', width: 90, align: 'right' },
]

const departmentColumns: ColumnSpec[] = [
  { key: 'code', title: '编码', width: 140 },
  { key: 'name', title: '名称' },
  { key: 'status', title: '状态', width: 90 },
  { key: 'created_at', title: '创建时间', width: 160 },
  { key: 'actions', title: '操作', width: 90, align: 'right' },
]

const bindingColumns: ColumnSpec[] = [
  { key: 'person_name', title: '姓名', width: 140 },
  { key: 'employee_no', title: '工号', width: 130 },
  { key: 'external_user_id', title: '外部用户标识', width: 180 },
  { key: 'display_name', title: '显示名', width: 140 },
  { key: 'status', title: '状态', width: 90 },
  { key: 'actions', title: '操作', width: 90, align: 'right' },
]

const TABS = [
  { key: 'persons', tab: '人员' },
  { key: 'departments', tab: '部门' },
  { key: 'bindings', tab: '租户人员绑定' },
]

const { read, write, filter } = useUrlFilters()
// 页签记在地址栏而不是模块级变量：刷新页面、把链接发给别人，落在的仍是同一个页签
const tab = filter('tab', 'persons')
/** 地址栏是外部输入：认不出的 tab 一律落到「人员」，别让页签高亮和面板对不上 */
const activeTab = computed(() =>
  TABS.some((item) => item.key === tab.value) ? tab.value : 'persons',
)

const shell = useShellStore()

const {
  data: page,
  loading,
  error,
  refresh,
} = useAsyncPage(
  async () => {
    const [persons, departments, tenants] = await Promise.all([
      orgApi.persons(200),
      // 部门与租户只服务另外两个页签：单独失败不该把整页变成错误面板（旧版就是 safe 兜底）
      safe(orgApi.departments(200), [] as Department[]),
      safe(tenantApi.list(200), [] as Tenant[]),
    ])
    shell.setCount('people', persons.length)
    return { persons, departments, tenants }
  },
  { persons: [] as Person[], departments: [] as Department[], tenants: [] as Tenant[] },
)

/** 绑定页签看哪个租户：地址栏里有就用它，否则落到第一个租户（旧版同口径）。 */
const bindTenantId = computed(() => read('tenant') || page.value.tenants[0]?.id || '')
/** 下拉里的待切换值：点了「切换」才写进地址栏，避免下拉一动就整表重查 */
const draftTenantId = ref('')

watch(
  bindTenantId,
  (value) => {
    draftTenantId.value = value
  },
  { immediate: true },
)

const {
  data: bindings,
  loading: bindingsLoading,
  error: bindingsError,
  refresh: refreshBindings,
} = useAsyncPage(
  async () =>
    activeTab.value === 'bindings' && bindTenantId.value
      ? await orgApi.tenantPersons(bindTenantId.value)
      : [],
  [] as TenantPersonBinding[],
)

// 切页签、换租户都要重新取绑定关系；不在绑定页签时不发请求
watch([tab, bindTenantId], () => void refreshBindings())

const personDialogOpen = ref(false)
const editingPerson = ref<Person | null>(null)
const departmentDialogOpen = ref(false)
const membersDialogOpen = ref(false)
const membersDepartment = ref<Department | null>(null)
const bindDialogOpen = ref(false)

onMounted(refresh)

function onTabChange(key: string | number): void {
  tab.value = String(key)
}

function openPersonDialog(person: Person | null): void {
  // 旧版列表里的「编辑」按钮没有对应处理函数，点了没反应；这里补上
  editingPerson.value = person
  personDialogOpen.value = true
}

function openMembers(department: Department): void {
  membersDepartment.value = department
  membersDialogOpen.value = true
}

function openDepartmentDialog(): void {
  departmentDialogOpen.value = true
}

function switchTenant(): void {
  write({ tenant: draftTenantId.value || null })
}

function openBindDialog(): void {
  if (!bindTenantId.value) {
    toastError('请先选择租户')
    return
  }
  bindDialogOpen.value = true
}

async function toggleBinding(binding: TenantPersonBinding): Promise<void> {
  const next = binding.status === 'ENABLED' ? 'DISABLED' : 'ENABLED'
  try {
    await orgApi.updateTenantPersonBinding(bindTenantId.value, binding.person_id, next)
    toastOk(next === 'ENABLED' ? '已启用' : '已停用')
    await refreshBindings()
  } catch (err) {
    toastError(errorMessageOf(err))
  }
}
</script>

<template>
  <PageHead
    title="人员与部门"
    note="第一版由管理台手工维护；接入项目平台后改为同步平台的人员和组织数据。"
  />

  <ErrorPanel v-if="error" :error="error" />

  <template v-else>
    <ATabs :active-key="activeTab" @change="onTabChange">
      <ATabPane v-for="item in TABS" :key="item.key" :tab="item.tab" />
    </ATabs>

    <PanelCard v-if="activeTab === 'persons'" title="全局人员">
      <template #actions>
        <ElButton size="small" type="primary" @click="openPersonDialog(null)">新建人员</ElButton>
      </template>
      <DataTable
        :columns="personColumns"
        :rows="page.persons"
        :loading="loading"
        empty-title="还没有人员"
        empty-hint="审批人和发起人都来自这里，先创建人员再配置审批流。"
      >
        <template #cell-mobile="{ row }">{{ row.mobile || '—' }}</template>
        <template #cell-email="{ row }">{{ row.email || '—' }}</template>
        <template #cell-status="{ row }">
          <StatusTag :status="row.status" />
        </template>
        <template #cell-id="{ row }">
          <span class="code">{{ row.id }}</span>
          <CopyButton :text="row.id" label="复制 ID" />
        </template>
        <template #cell-actions="{ row }">
          <button class="btn--link btn--sm" type="button" @click="openPersonDialog(row)">
            编辑
          </button>
        </template>
        <template #empty-action>
          <ElButton type="primary" size="small" @click="openPersonDialog(null)">新建人员</ElButton>
        </template>
      </DataTable>
    </PanelCard>

    <PanelCard v-else-if="activeTab === 'departments'" title="部门">
      <template #actions>
        <ElButton size="small" type="primary" @click="openDepartmentDialog">新建部门</ElButton>
      </template>
      <DataTable
        :columns="departmentColumns"
        :rows="page.departments"
        :loading="loading"
        empty-title="还没有部门"
        empty-hint="第一版部门为全局平铺结构，用于按部门查看和核对人员。"
      >
        <template #cell-status="{ row }">
          <StatusTag :status="row.status" />
        </template>
        <template #cell-created_at="{ row }">{{ formatTime(row.created_at) }}</template>
        <template #cell-actions="{ row }">
          <button class="btn--link btn--sm" type="button" @click="openMembers(row)">成员</button>
        </template>
        <template #empty-action>
          <ElButton type="primary" size="small" @click="openDepartmentDialog">新建部门</ElButton>
        </template>
      </DataTable>
    </PanelCard>

    <PanelCard v-else title="租户人员绑定">
      <div class="bind-bar">
        <div class="field">
          <label class="field__label">租户</label>
          <ElSelect v-model="draftTenantId" style="width: 200px">
            <ElOption
              v-for="tenant in page.tenants"
              :key="tenant.id"
              :value="tenant.id"
              :label="tenant.name"
            />
          </ElSelect>
        </div>
        <ElButton @click="switchTenant">切换</ElButton>
        <ElButton type="primary" @click="openBindDialog">绑定人员</ElButton>
      </div>

      <div v-if="bindingsError" class="note note--wait">{{ bindingsError.message }}</div>

      <DataTable
        v-else
        :columns="bindingColumns"
        :rows="bindings"
        :loading="bindingsLoading"
        empty-title="该租户还没有绑定人员"
        empty-hint="绑定后可以把人员与租户内的工号、外部账号对应起来。"
      >
        <template #cell-employee_no="{ row }">{{ row.employee_no || '—' }}</template>
        <template #cell-external_user_id="{ row }">{{ row.external_user_id || '—' }}</template>
        <template #cell-display_name="{ row }">{{ row.display_name || '—' }}</template>
        <template #cell-status="{ row }">
          <StatusTag :status="row.status" />
        </template>
        <template #cell-actions="{ row }">
          <button class="btn--link btn--sm" type="button" @click="toggleBinding(row)">
            {{ row.status === 'ENABLED' ? '停用' : '启用' }}
          </button>
        </template>
      </DataTable>
    </PanelCard>

    <PersonFormDialog v-model:open="personDialogOpen" :person="editingPerson" @saved="refresh" />
    <DepartmentFormDialog v-model:open="departmentDialogOpen" @saved="refresh" />
    <DepartmentMembersDialog
      v-model:open="membersDialogOpen"
      :department="membersDepartment"
      :persons="page.persons"
      @changed="refresh"
    />
    <TenantPersonBindDialog
      v-model:open="bindDialogOpen"
      :tenant-id="bindTenantId"
      :persons="page.persons"
      @saved="refreshBindings"
    />
  </template>
</template>

<style scoped>
/* 绑定页签的筛选行：旧版用的是整条 .filters 带（自带 padding 与底色），
   放进 PanelCard 的 body 里会多一层内边距，所以这里只保留排版 */
.bind-bar {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
</style>
