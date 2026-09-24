import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it } from 'vitest'

import BranchDialog from '@/components/flow/BranchDialog.vue'
import type { FlowConnection, FlowNode, JSONSchema } from '@/types/domain'

const FORM_SCHEMA: JSONSchema = {
  type: 'object',
  properties: {
    amount: { type: 'number', title: '付款金额' },
    level: { type: 'string', title: '级别', enum: ['NORMAL', 'URGENT'] },
  },
}

const NODES: FlowNode[] = [
  {
    id: 'branch',
    node_definition_id: 'def-condition',
    node_type: 'CONDITION',
    node_definition_name: '条件分支',
    name: '按金额分流',
    config: {},
    position: { x: 0, y: 0 },
  },
  {
    id: 'boss',
    node_definition_id: 'def-approval',
    node_type: 'APPROVAL',
    node_definition_name: '人工审批',
    name: '总经理审批',
    config: {},
    position: { x: 400, y: 0 },
  },
  {
    id: 'end',
    node_definition_id: 'def-end',
    node_type: 'END',
    node_definition_name: '结束',
    name: '审批通过',
    config: {},
    position: { x: 800, y: 0 },
  },
]

const CONNECTIONS: FlowConnection[] = [
  {
    source_node_id: 'branch',
    target_node_id: 'boss',
    condition: { field: 'approval_form.amount', operator: 'GT', value: 10000 },
  },
  { source_node_id: 'branch', target_node_id: null },
]

function mountDialog(schema: JSONSchema = FORM_SCHEMA) {
  return mount(BranchDialog, {
    props: {
      open: true,
      node: NODES[0],
      nodes: NODES,
      connections: CONNECTIONS,
      formSchema: schema,
    },
    attachTo: document.body,
  })
}

describe('条件分支编辑器', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('按现有出线列出阶梯，最后一条是「其余情况」', async () => {
    const wrapper = mountDialog()
    await nextTick()

    const rows = document.body.querySelectorAll('.branch-row')
    expect(rows).toHaveLength(2)
    expect(rows[0].textContent).toContain('条件 1')
    expect(rows[1].textContent).toContain('其余情况')
    // 其余情况那一行没有字段下拉，只有一句说明
    expect(rows[1].textContent).toContain('上面的条件都不满足时走这条')
    wrapper.unmount()
  })

  it('去向是只读的：显示目标名，没接的显示「未接去向」', async () => {
    const wrapper = mountDialog()
    await nextTick()

    const targets = Array.from(document.body.querySelectorAll('.branch-row__target'))
    expect(targets[0].textContent).toContain('总经理审批')
    expect(targets[1].textContent).toContain('未接去向')
    expect(targets[1].className).toContain('is-unlinked')
    // 弹窗里不该出现任何选择去向的下拉
    expect(document.body.innerHTML).not.toContain('选择去向')
    wrapper.unmount()
  })

  it('「新增条件」插在其余情况之前', async () => {
    const wrapper = mountDialog()
    await nextTick()

    const addButton = Array.from(document.body.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('新增条件'),
    )
    addButton?.click()
    await nextTick()

    const rows = document.body.querySelectorAll('.branch-row')
    expect(rows).toHaveLength(3)
    expect(rows[1].textContent).toContain('条件 2')
    expect(rows[2].textContent).toContain('其余情况')
    wrapper.unmount()
  })

  it('契约③：保存时最后一条恒为「其余情况」，不带 condition', async () => {
    const wrapper = mountDialog()
    await nextTick()

    const saveButton = Array.from(document.body.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('保存'),
    )
    saveButton?.click()
    await nextTick()

    const emitted = wrapper.emitted('save')?.[0]?.[0] as Array<{
      target_node_id: string | null
      condition: unknown
    }>
    expect(emitted).toHaveLength(2)
    expect(emitted[0].condition).toMatchObject({ field: 'approval_form.amount', operator: 'GT' })
    expect(emitted[1].condition).toBeNull()
    expect(emitted[1].target_node_id).toBeNull()
    wrapper.unmount()
  })

  it('中间一条没配字段时拦下保存并提示是第几条', async () => {
    const wrapper = mount(BranchDialog, {
      props: {
        open: true,
        node: NODES[0],
        nodes: NODES,
        connections: [
          { source_node_id: 'branch', target_node_id: 'boss' },
          { source_node_id: 'branch', target_node_id: 'end' },
        ],
        formSchema: FORM_SCHEMA,
      },
      attachTo: document.body,
    })
    await nextTick()

    const saveButton = Array.from(document.body.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('保存'),
    )
    saveButton?.click()
    await nextTick()

    expect(wrapper.emitted('save')).toBeUndefined()
    expect(document.body.textContent).toContain('条件 1')
    expect(document.body.textContent).toContain('还没有配完')
    wrapper.unmount()
  })

  it('流程还没有表单字段时给出引导，而不是空下拉', async () => {
    const wrapper = mountDialog({ type: 'object', properties: {} })
    await nextTick()

    expect(document.body.textContent).toContain('还没有定义表单字段')
    expect(document.body.querySelectorAll('.branch-row')).toHaveLength(0)
    wrapper.unmount()
  })
})
