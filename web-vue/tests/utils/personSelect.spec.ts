import { describe, expect, it } from 'vitest'

import { filterPersonOptions, matchesPersonQuery, type PersonOption } from '@/utils/personSelect'

const PEOPLE: PersonOption[] = [
  {
    value: 'p1',
    label: '李清波',
    departments: ['技术部门'],
    mobile: '13800000001',
    email: 'li@example.com',
  },
  { value: 'p2', label: '陈柱弛', departments: ['技术部门', '财务部'] },
  { value: 'p3', label: '王小明', departments: [] },
]

function matched(query: string): string[] {
  return filterPersonOptions(PEOPLE, query).map((option) => option.value)
}

describe('选人下拉的搜索口径', () => {
  it('空查询不过滤：下拉打开时看到的是全部人', () => {
    expect(matched('')).toEqual(['p1', 'p2', 'p3'])
    expect(matched('   ')).toEqual(['p1', 'p2', 'p3'])
  })

  it('按姓名搜，片段命中即可', () => {
    expect(matched('柱弛')).toEqual(['p2'])
    expect(matched('王')).toEqual(['p3'])
  })

  it('按部门搜：搜部门名能把该部门的人都捞出来', () => {
    expect(matched('技术部门')).toEqual(['p1', 'p2'])
    expect(matched('财务')).toEqual(['p2'])
  })

  it('按手机号、邮箱搜', () => {
    expect(matched('13800000001')).toEqual(['p1'])
    expect(matched('li@example')).toEqual(['p1'])
  })

  it('不区分大小写，也不去匹配没填的字段', () => {
    expect(matched('LI@EXAMPLE')).toEqual(['p1'])
    expect(matched('不存在的部门')).toEqual([])
  })

  it('没有部门的人只按姓名匹配，不会因为缺字段报错', () => {
    const option: PersonOption = { value: 'p9', label: '无部门' }
    expect(matchesPersonQuery(option, '无部门')).toBe(true)
    expect(matchesPersonQuery(option, '技术')).toBe(false)
  })
})
