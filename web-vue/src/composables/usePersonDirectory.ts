import { computed, onMounted, ref, shallowRef, type Ref } from 'vue'

import { safe } from '@/api/http'
import { orgApi } from '@/api/modules/org'
import type { Person } from '@/api/types'
import type { PersonOption } from '@/utils/personSelect'

/** 人员目录：全局人员 + 每个人所属部门（拼成选人下拉要的选项）。 */
export interface PersonDirectory {
  persons: Person[]
  options: PersonOption[]
}

const EMPTY: PersonDirectory = { persons: [], options: [] }

/**
 * 目录按模块缓存一份。
 *
 * 人员与部门变动不频繁，而选人的地方有五处（节点的审批人、发起审批的发起人、
 * 部门成员、租户绑定人员、审批任务的人员筛选），每开一次弹窗都重拉一遍没必要。
 * 代价是写入之后要显式失效 —— 人员、部门、部门成员有改动的地方调
 * `invalidatePersonDirectory()`，下一次选人自然会重取。
 */
let cached: Promise<PersonDirectory> | null = null

export function invalidatePersonDirectory(): void {
  cached = null
}

export function loadPersonDirectory(): Promise<PersonDirectory> {
  cached ??= fetchPersonDirectory().catch((error: unknown) => {
    // 失败不进缓存：一次网络抖动不该被后面所有调用当成同一个结果复用
    cached = null
    throw error
  })
  return cached
}

async function fetchPersonDirectory(): Promise<PersonDirectory> {
  const [persons, departments] = await Promise.all([orgApi.persons(200), orgApi.departments(200)])

  // 后端没有"按人查部门"的接口（人员响应里没有部门字段），只能按部门扇出再按人合并 ——
  // 与本工程其它地方「拉全量再前端合并」的取数方式一致。
  // 单个部门查失败不该让整个选人控件瘫掉，退化成"这些人没有部门标签"。
  const memberLists = await Promise.all(
    departments.map((department) => safe(orgApi.departmentMembers(department.id), [])),
  )

  const departmentsOf = new Map<string, string[]>()
  for (const member of memberLists.flat()) {
    if (member.status !== 'ENABLED') continue
    const names = departmentsOf.get(member.person_id) ?? []
    if (!names.includes(member.department_name)) names.push(member.department_name)
    departmentsOf.set(member.person_id, names)
  }

  return {
    persons,
    // 选项里不要停用的人：选人都是在挑审批人、发起人、成员，挑到停用的人没法往下走。
    // 停用的人仍留在 persons 里 —— 翻历史记录的审批人姓名还要用（任务可能属于已停用的人）。
    options: persons
      .filter((person) => person.status === 'ENABLED')
      .map((person) => ({
        value: person.id,
        label: person.name,
        departments: departmentsOf.get(person.id) ?? [],
        mobile: person.mobile,
        email: person.email,
      })),
  }
}

/**
 * 组件里用的人员目录：挂载时自动取一次（有缓存就直接用缓存）。
 * 只需要原始人员列表的用 persons，要喂给选人控件的用 options。
 */
export function usePersonDirectory(): {
  persons: Ref<Person[]>
  options: Ref<PersonOption[]>
  loading: Ref<boolean>
  error: Ref<Error | null>
  refresh: () => Promise<void>
} {
  const directory = shallowRef<PersonDirectory>(EMPTY)
  const loading = ref(false)
  const error = ref<Error | null>(null)

  async function refresh(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      directory.value = await loadPersonDirectory()
    } catch (err) {
      error.value = err instanceof Error ? err : new Error(String(err))
    } finally {
      loading.value = false
    }
  }

  onMounted(refresh)

  return {
    persons: computed(() => directory.value.persons),
    options: computed(() => directory.value.options),
    loading,
    error,
    refresh,
  }
}
