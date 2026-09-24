import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import App from '@/App.vue'
import { NAV, routes } from '@/router/routes'

/** 用内存路由挂载整个壳，验证「导航可点、路由可切」这条阶段 0 的验收标准。 */
async function mountShell(initialPath = '/overview') {
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(initialPath)
  await router.isReady()

  const wrapper = mount(App, { global: { plugins: [router] } })
  await router.isReady()
  return { wrapper, router }
}

describe('控制台外壳', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('左侧导航按分组渲染出全部入口', async () => {
    const { wrapper } = await mountShell()
    const groups = wrapper.findAll('.rail__group').map((node) => node.text())
    expect(groups).toEqual(NAV.map((group) => group.group))

    const items = wrapper.findAll('.rail__item')
    expect(items).toHaveLength(NAV.reduce((total, group) => total + group.items.length, 0))
    expect(items.map((node) => node.text())).toContain('审批流')
  })

  it('顶栏有接口地址与管理密钥两个输入框', async () => {
    const { wrapper } = await mountShell()
    expect(wrapper.find('.topbar__input--wide').exists()).toBe(true)
    expect(wrapper.find('.topbar__input--key').attributes('placeholder')).toBe('X-Admin-Key')
    expect(wrapper.find('.link-state').text()).toContain('未连接')
  })

  it('切换路由时高亮跟着走，子页面归到父导航项', async () => {
    const { wrapper, router } = await mountShell()
    const activeLabels = () => wrapper.findAll('.rail__item--active').map((node) => node.text())

    expect(activeLabels()[0]).toContain('闭环进度')

    await router.push('/tenants')
    expect(activeLabels()[0]).toContain('租户')

    // 版本编辑器挂在「审批流」下，审批详情挂在「审批任务」下
    await router.push('/versions/41000000-0000-4000-8000-000000000002')
    expect(activeLabels()[0]).toContain('审批流')

    await router.push('/instances/70000000-0000-4000-8000-000000000001')
    expect(activeLabels()[0]).toContain('审批任务')
  })

  it('页面标题随路由变化', async () => {
    const { wrapper, router } = await mountShell()
    expect(wrapper.find('.page-head__title').text()).toBe('闭环进度')

    await router.push('/definitions')
    expect(wrapper.find('.page-head__title').text()).toBe('节点定义')
  })
})
