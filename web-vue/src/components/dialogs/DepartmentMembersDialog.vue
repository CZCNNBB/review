<script setup lang="ts">
import { ElButton } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { orgApi } from '@/api/modules/org'
import type { Department, DepartmentMember } from '@/api/types'
import AppDialog from '@/components/common/AppDialog.vue'
import DataTable from '@/components/common/DataTable.vue'
import type { ColumnSpec } from '@/components/common/DataTable.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import PersonSelect from '@/components/form/PersonSelect.vue'
import { useAsyncPage } from '@/composables/useAsyncPage'
import { invalidatePersonDirectory, usePersonDirectory } from '@/composables/usePersonDirectory'
import { errorMessageOf } from '@/composables/useConfirm'
import { formatTime } from '@/utils/format'
import { toastError, toastOk } from '@/utils/notify'

// 部门成员。旧版这个弹窗是一次性的：加一个人就关窗重渲染整页，想连加几个人得重复打开。
// 这一版改成留在窗口里就地刷新，成员表本身也跟着更新。
const open = defineModel<boolean>('open', { default: false })

const props = defineProps<{
  department?: Department | null
}>()

const emit = defineEmits<{ (event: 'changed'): void }>()

// 候选人员：走人员目录（带部门标签），不再由页面传 persons 进来
const directory = usePersonDirectory()

const columns: ColumnSpec[] = [
  { key: 'person_name', title: '姓名', width: 140 },
  { key: 'created_at', title: '加入时间', width: 160 },
  { key: 'status', title: '状态', width: 90 },
  { key: 'actions', title: '操作', width: 90, align: 'right' },
]

const {
  data: members,
  loading,
  error,
  refresh,
} = useAsyncPage(async () => {
  if (!props.department) return []
  return await orgApi.departmentMembers(props.department.id)
}, [] as DepartmentMember[])

const pickedPersonId = ref('')
const busy = ref(false)

const memberIds = computed(
  () =>
    new Set(
      members.value
        .filter((member) => member.status === 'ENABLED')
        .map((member) => member.person_id),
    ),
)

/**
 * 可加入的人：启用中、且还没在该部门里的人。
 * 故意只排除仍在部门里的成员 —— 旧版连停用过的成员一起排除，而下拉里又没有「恢复」，
 * 结果就是成员一旦被停用就再也加不回来（后端重新添加其实会把关系重新启用）。
 * 候选来自人员目录（带部门标签，能看出这个人是不是已经在别的部门了）。
 */
const available = computed(() =>
  directory.options.value.filter((option) => !memberIds.value.has(option.value)),
)

watch(open, (isOpen) => {
  if (!isOpen) return
  pickedPersonId.value = ''
  void refresh()
})

async function addMember(): Promise<void> {
  if (!props.department || !pickedPersonId.value) return
  busy.value = true
  try {
    await orgApi.addDepartmentMember(props.department.id, pickedPersonId.value)
    pickedPersonId.value = ''
    invalidatePersonDirectory()
    toastOk('成员已添加')
    await refresh()
    emit('changed')
  } catch (err) {
    toastError(errorMessageOf(err))
  } finally {
    busy.value = false
  }
}

async function disableMember(member: DepartmentMember): Promise<void> {
  if (!props.department) return
  busy.value = true
  try {
    await orgApi.disableDepartmentMember(props.department.id, member.person_id)
    invalidatePersonDirectory()
    toastOk('成员关系已停用')
    await refresh()
    emit('changed')
  } catch (err) {
    toastError(errorMessageOf(err))
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AppDialog
    v-model:open="open"
    :title="`${props.department?.name || '部门'} · 成员`"
    width="640px"
  >
    <div class="member-add">
      <PersonSelect
        v-model="pickedPersonId"
        :options="available"
        placeholder="搜索姓名或部门…"
        :disabled="busy"
      />
      <ElButton type="primary" :loading="busy" @click="addMember">添加</ElButton>
    </div>

    <div v-if="error" class="note note--wait">{{ error.message }}</div>

    <DataTable
      v-else
      :columns="columns"
      :rows="members"
      :loading="loading"
      row-key="person_id"
      empty-title="该部门还没有成员"
      empty-hint="从上面的下拉里选一个人加进来。"
    >
      <template #cell-created_at="{ row }">{{ formatTime(row.created_at) }}</template>
      <template #cell-status="{ row }">
        <StatusTag :status="row.status" />
      </template>
      <template #cell-actions="{ row }">
        <button
          v-if="row.status === 'ENABLED'"
          class="btn--link btn--sm is-danger"
          type="button"
          :disabled="busy"
          @click="disableMember(row)"
        >
          停用
        </button>
      </template>
    </DataTable>

    <template #footer>
      <ElButton @click="open = false">关闭</ElButton>
    </template>
  </AppDialog>
</template>

<style scoped>
.member-add {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}
</style>
