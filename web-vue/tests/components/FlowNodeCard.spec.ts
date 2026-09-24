import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import FlowNodeCard from '@/components/flow/FlowNodeCard.vue'
import type { FlowConnection, FlowNode } from '@/types/domain'
import { buildCanvasModel, type CanvasNodeVM } from '@/utils/flowCanvasModel'

function node(over: Partial<FlowNode> & { id: string }): FlowNode {
  return {
    node_definition_id: `def-${over.id}`,
    node_type: 'APPROVAL',
    name: over.id,
    config: {},
    position: { x: 0, y: 0 },
    ...over,
  }
}

const NODES: FlowNode[] = [
  node({ id: 'start', node_type: 'START', name: '开始' }),
  node({ id: 'branch', node_type: 'CONDITION', name: '按金额分流' }),
  node({ id: 'approval', node_type: 'APPROVAL', name: '领导审批' }),
  node({ id: 'end', node_type: 'END', name: '结束' }),
]

const CONNECTIONS: FlowConnection[] = [
  { source_node_id: 'start', target_node_id: 'branch' },
  {
    source_node_id: 'branch',
    target_node_id: 'approval',
    condition: { field: 'approval_form.amount', operator: 'GT', value: 1000 },
  },
  { source_node_id: 'branch', target_node_id: 'end' },
]

function modelOf(id: string, editable = true): CanvasNodeVM {
  const model = buildCanvasModel(NODES, CONNECTIONS, { editable, fieldLabels: {} })
  return model.nodes.find((item) => item.node.id === id) as CanvasNodeVM
}

function mountCard(id: string, editable = true) {
  return mount(FlowNodeCard, {
    props: { model: modelOf(id, editable), editable },
    attachTo: document.body,
  })
}

describe('节点卡上的按钮与分支行', () => {
  /**
   * 画布的 pointerdown 会把卡片内的按下一律当成"选中/拖动"并抢走指针捕获，
   * 于是按钮自己的 click 不会再触发 —— 表现就是点「删除」弹出编辑弹窗。
   * 旧版靠 data-act 让画布提前放手，这几个属性是这条通路的唯一开关。
   */
  it('工具按钮带 data-act，画布才会把点击让给它', () => {
    const wrapper = mountCard('approval')

    expect(wrapper.find('[data-act="edit-node"]').exists()).toBe(true)
    expect(wrapper.find('[data-act="drop-node"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('按钮点了发对应的事件，不是笼统一个 click', async () => {
    const wrapper = mountCard('approval')

    await wrapper.find('[data-act="edit-node"]').trigger('click')
    await wrapper.find('[data-act="drop-node"]').trigger('click')

    expect(wrapper.emitted('edit')).toHaveLength(1)
    expect(wrapper.emitted('delete')).toHaveLength(1)
    wrapper.unmount()
  })

  it('开始节点没有删除按钮（流程只能有一个入口）', () => {
    const wrapper = mountCard('start')

    expect(wrapper.find('[data-act="drop-node"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('分支行与「＋ 新增分支」都带 data-act=edit-branch', () => {
    const wrapper = mountCard('branch')
    const rows = wrapper.findAll('.flow__row')

    // 两条分支 + 新增分支那一行
    expect(rows).toHaveLength(3)
    expect(rows.every((row) => row.attributes('data-act') === 'edit-branch')).toBe(true)
    wrapper.unmount()
  })

  it('只读版本：工具按钮、分支行出口、节点出口一概不给', () => {
    const wrapper = mountCard('approval', false)

    expect(wrapper.find('.flow__node-tools').exists()).toBe(false)
    expect(wrapper.find('.flow__port--out').exists()).toBe(false)
    expect(wrapper.find('.flow__port--in').exists()).toBe(false)
    wrapper.unmount()
  })

  it('条件分支卡片的出口全在分支行上，卡片本体不给出口', () => {
    const branch = mountCard('branch')
    expect(branch.find('.flow__row-port').exists()).toBe(true)
    expect(branch.find('.flow__port--out').exists()).toBe(false)
    branch.unmount()

    // 结束节点有进无出
    const end = mountCard('end')
    expect(end.find('.flow__port--in').exists()).toBe(true)
    expect(end.find('.flow__port--out').exists()).toBe(false)
    end.unmount()
  })
})
