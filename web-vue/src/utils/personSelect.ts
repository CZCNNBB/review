/**
 * 选人下拉的选项与搜索口径。
 *
 * 选项除了姓名还带上所属部门：重名的人靠它区分，搜索时也能按部门捞人
 * （"技术部有哪些人"直接搜部门名就行）。
 *
 * 部门不在人员接口里 —— 后端只提供「按部门查成员」，所以这个字段要靠
 * 部门成员关系反向合并出来，见 composables/usePersonDirectory.ts。
 */
export interface PersonOption {
  value: string
  label: string
  /** 所属部门名，可能多个；没有部门就是空数组 */
  departments?: string[]
  mobile?: string | null
  email?: string | null
}

/**
 * 搜索口径：姓名、部门、手机号、邮箱任意一段命中即可，大小写不敏感。
 * 空查询视为不过滤（下拉打开时应当看到全部人）。
 */
export function matchesPersonQuery(option: PersonOption, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  return [option.label, ...(option.departments ?? []), option.mobile ?? '', option.email ?? ''].some(
    (text) => text.toLowerCase().includes(needle),
  )
}

export function filterPersonOptions(options: PersonOption[], query: string): PersonOption[] {
  return options.filter((option) => matchesPersonQuery(option, query))
}
