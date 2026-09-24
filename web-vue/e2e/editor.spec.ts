import { expect } from '@playwright/test'

import {
  boxInView,
  draftOf,
  dragBy,
  fitCanvas,
  nodeCard,
  openVersion,
  paletteItem,
  publishedOf,
  test,
  type GraphNode,
} from './backend'

/**
 * 版本编辑器的契约往返。
 * 契约①（工作副本不丢）与契约⑦（只读版本）在这里走完整链路验证。
 */

/** 状态标签里「草稿」也是 .tag--wait，按文字认人，别按类名。 */
const dirtyTag = (page: import('@playwright/test').Page) =>
  page.locator('.tag--wait').filter({ hasText: '有未保存的改动' })

test.describe('版本编辑器', () => {
  test('契约①：切页签、开弹窗都不丢未保存的改动；离开路由才丢弃', async ({
    page,
    target,
  }) => {
    const draft = draftOf(target)
    await openVersion(page, target, draft.id)
    await fitCanvas(page)

    const cards = page.locator('.flow__stage .flow__node')
    const nodesBefore = await cards.count()

    // 从面板点一个节点进来（面板的拖影也带 .flow__node，所以要限定在画布里数）
    await paletteItem(page).click()
    await expect(page.locator('.el-dialog')).toBeVisible()
    await page.locator('.el-dialog button').filter({ hasText: '添加节点' }).click()
    await expect(cards).toHaveCount(nodesBefore + 1)

    // 切到「编排数据」再切回来，改动仍在，并显示未保存标记
    await page.locator('button').filter({ hasText: '编排数据' }).click()
    await expect(dirtyTag(page)).toBeVisible()
    await page.locator('button').filter({ hasText: '审批表单' }).click()
    await expect(cards).toHaveCount(nodesBefore + 1)

    // 打开节点配置弹窗再关掉，改动同样不受影响
    const node = draft.nodes[0] as GraphNode
    await dragBy(page, await boxInView(nodeCard(page, node.id)), 1, 1)
    await expect(page.locator('.el-dialog__title')).toContainText('编辑节点')
    await page.locator('.el-dialog button').filter({ hasText: '取消' }).click()
    await expect(cards).toHaveCount(nodesBefore + 1)

    // 离开编辑器路由：工作副本丢弃，回来是接口里的原始数据
    await page.locator('.rail__item').filter({ hasText: '审批流' }).click()
    await expect(page).toHaveURL(/#\/processes/)
    await openVersion(page, target, draft.id)
    await expect(cards).toHaveCount(nodesBefore)
  })

  test('契约①：保存成功后工作副本重建，未保存标记消失', async ({ page, target }) => {
    // 这条会把改过的图 PUT 回后端，开发库是共用的，所以默认不跑
    test.skip(process.env.E2E_ALLOW_WRITES !== '1', '会写库：要跑请设 E2E_ALLOW_WRITES=1')
    const draft = draftOf(target)
    await openVersion(page, target, draft.id)
    await fitCanvas(page)

    const node = draft.nodes.find((item) => item.node_type !== 'CONDITION') as GraphNode

    /** 改节点名 → 保存草稿，返回时草稿已按接口返回重建。 */
    async function renameAndSave(name: string): Promise<void> {
      await dragBy(page, await boxInView(nodeCard(page, node.id)), 1, 1)
      await expect(page.locator('.el-dialog__title')).toContainText('编辑节点')
      await page.locator('.el-dialog input[type="text"]').first().fill(name)
      await page.locator('.el-dialog button').filter({ hasText: '保存节点' }).click()
      await expect(dirtyTag(page)).toBeVisible()
      await page.locator('button').filter({ hasText: '保存草稿' }).click()
      await expect(page.locator('.el-message').filter({ hasText: '草稿已保存' })).toBeVisible()
    }

    await renameAndSave('契约①改名验证')
    // 保存成功会拿接口返回的图重建工作副本，标记随之消失
    await expect(dirtyTag(page)).toHaveCount(0)

    // 收尾：名字改回去。写的是共用的开发库，别把痕迹留在上面（修订号涨一次躲不掉）
    await expect(nodeCard(page, node.id)).toContainText('契约①改名验证')
    await renameAndSave(node.name)
    await expect(nodeCard(page, node.id)).toContainText(node.name)
  })

  test('契约⑦：已发布版本只读——没有保存/发布，画布不给出口圆点', async ({
    page,
    target,
  }) => {
    await openVersion(page, target, publishedOf(target))
    await fitCanvas(page)

    await expect(page.locator('button').filter({ hasText: '保存草稿' })).toHaveCount(0)
    await expect(page.locator('button').filter({ hasText: '发布' })).toHaveCount(0)
    await expect(page.locator('.flow-palette__hint')).toContainText('已发布版本只读')

    // 悬停也不该出现出口圆点
    await page.locator('.flow__stage .flow__node').first().hover()
    await expect(page.locator('.flow__port--out')).toHaveCount(0)
  })
})
