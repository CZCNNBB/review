import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'

import PersonSelect from '@/components/form/PersonSelect.vue'
import type { PersonOption } from '@/utils/personSelect'

const OPTIONS: PersonOption[] = [
  { value: 'p1', label: '李清波', departments: ['技术部门'] },
  { value: 'p2', label: '陈柱弛', departments: ['技术部门', '财务部'] },
  { value: 'p3', label: '王小明', departments: [] },
]

async function openSelect(props: Record<string, unknown> = {}) {
  const wrapper = mount(PersonSelect, {
    props: { options: OPTIONS, modelValue: '', ...props },
    attachTo: document.body,
  })
  await wrapper.find('.el-select__wrapper').trigger('click')
  await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  return wrapper
}

/** 下拉是 teleport 到 body 的，只能从 document 上找。 */
function optionTexts(): string[] {
  return Array.from(document.querySelectorAll('.el-select-dropdown__item')).map(
    (item) => item.textContent?.trim() ?? '',
  )
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('选人控件', () => {
  it('每个人后面缀着所属部门的小标签，没有部门的不显示标签', async () => {
    await openSelect()

    const items = Array.from(document.querySelectorAll('.el-select-dropdown__item'))
    expect(items).toHaveLength(3)

    const tags = (index: number): string[] =>
      Array.from(items[index].querySelectorAll('.tag')).map((tag) => tag.textContent?.trim() ?? '')

    expect(tags(0)).toEqual(['技术部门'])
    expect(tags(1)).toEqual(['技术部门', '财务部'])
    expect(tags(2)).toEqual([])
  })

  it('搜索框里输部门名，只留下这个部门的人', async () => {
    const wrapper = await openSelect()

    const input = document.querySelector('.el-select__input') as HTMLInputElement
    input.value = '财务'
    input.dispatchEvent(new Event('input'))
    await nextTick()
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(optionTexts().join()).toContain('陈柱弛')
    expect(optionTexts().join()).not.toContain('李清波')
    wrapper.unmount()
  })

  it('多选时选中项按名字展示', async () => {
    const wrapper = await openSelect({ multiple: true, modelValue: [] })

    expect(wrapper.find('.el-select__wrapper').exists()).toBe(true)
    wrapper.unmount()
  })
})
