import { mount } from '@vue/test-utils'
import { ElInput, ElOption, ElSelect } from 'element-plus'
import { describe, expect, it } from 'vitest'

import DynamicForm from '@/components/form/DynamicForm.vue'
import type { DynamicFieldSpec } from '@/utils/nodeConfigForm'

const FIELDS: DynamicFieldSpec[] = [
  { name: 'name', label: '节点名称', type: 'text', placeholder: '人工审批' },
  {
    name: 'approval_mode',
    label: '审批模式 *',
    type: 'select',
    required: true,
    options: [
      { value: 'AND', label: 'AND' },
      { value: 'OR', label: 'OR' },
    ],
  },
  { name: 'approvers', label: '审批人 *', type: 'multiselect', required: true, options: [] },
]

function mountForm(values: Record<string, unknown>) {
  return mount(DynamicForm, {
    props: { fields: FIELDS, modelValue: values, 'onUpdate:modelValue': () => {} },
    global: { components: { ElInput, ElSelect, ElOption } },
  })
}

describe('通用动态表单', () => {
  it('按字段描述符渲染控件，并把当前取值填进去', () => {
    const wrapper = mountForm({ name: '财务审批', approval_mode: 'OR', approvers: [] })
    const html = wrapper.html()

    expect(html).toContain('节点名称')
    expect(html).toContain('审批模式')
    expect((wrapper.find('input[type="text"]').element as HTMLInputElement).value).toBe('财务审批')
  })

  it('回归：必填为空要拦住提交，并给出和旧版一致的文案', async () => {
    // 曾经依赖 ElForm 的表单级校验，而它在空值时也返回通过 —— 必填形同虚设。
    // 现在由组件自己判定，这条钉住它。
    const wrapper = mountForm({ name: '', approval_mode: '', approvers: [] })

    await expect(wrapper.vm.validate()).resolves.toBe(false)
    expect(wrapper.text()).toContain('审批模式不能为空')

    // 空数组也算没填
    expect(wrapper.text()).toContain('审批模式不能为空')
  })

  it('值齐了校验就通过', async () => {
    const wrapper = mountForm({ name: 'x', approval_mode: 'AND', approvers: ['p1'] })
    await expect(wrapper.vm.validate()).resolves.toBe(true)
  })

  it('必填通过后清掉上一次的错误', async () => {
    const wrapper = mountForm({ name: '', approval_mode: '', approvers: [] })
    await expect(wrapper.vm.validate()).resolves.toBe(false)

    await wrapper.setProps({ modelValue: { name: '', approval_mode: 'OR', approvers: ['p1'] } })
    await expect(wrapper.vm.validate()).resolves.toBe(true)
    expect(wrapper.text()).not.toContain('不能为空')
  })

  it('note 字段渲染成说明，带按钮时点一下把动作交给调用方', async () => {
    const wrapper = mount(DynamicForm, {
      props: {
        fields: [
          {
            name: '__note',
            label: '',
            type: 'note',
            text: '条件分支的规则不在这个窗口里配。',
            action: { kind: 'goto-branch', label: '去配置分支', nodeId: 'n3' },
          },
        ],
        modelValue: {},
        'onUpdate:modelValue': () => {},
      },
      global: { components: { ElInput, ElSelect, ElOption } },
    })

    expect(wrapper.text()).toContain('条件分支的规则不在这个窗口里配')
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('note-action')?.[0]?.[0]).toEqual({
      kind: 'goto-branch',
      label: '去配置分支',
      nodeId: 'n3',
    })
  })

  it('错误信息显示在表单底部', () => {
    const wrapper = mount(DynamicForm, {
      props: { fields: FIELDS, modelValue: {}, error: '审批人 不能为空', 'onUpdate:modelValue': () => {} },
      global: { components: { ElInput, ElSelect, ElOption } },
    })
    expect(wrapper.text()).toContain('审批人 不能为空')
  })
})
