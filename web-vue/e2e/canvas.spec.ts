import { expect } from '@playwright/test'

import {
  boxInView,
  draftOf,
  dragBy,
  dropPaletteItem,
  edgePaths,
  fitCanvas,
  nodeCard,
  openVersion,
  paletteItem,
  test,
  type GraphNode,
} from './backend'

/**
 * 画布交互的端到端用例。
 *
 * 这几条契约在 jsdom 里测不了（DataTransfer 不存在、elementFromPoint 返回 null），
 * 只能上真浏览器：拖节点、拉线（普通出口 / 分支行出口 / 新增分支）、面板拖入，
 * 以及"位移≤2px 算点击"。
 *
 * 每个用例开头都点一次「适应」：画布是可滚动的，不先把整张图缩进视口，
 * 边上节点的坐标会落在可视区外，鼠标点过去打不到它。
 */

/** 已经有一条出线的普通节点 —— 契约④要拿它试「再拉一条」。 */
function nodeWithOutgoing(nodes: GraphNode[], connections: { source_node_id: string }[]) {
  return nodes.find(
    (node) =>
      !['START', 'END', 'CONDITION'].includes(node.node_type) &&
      connections.some((connection) => connection.source_node_id === node.id),
  )
}

test.describe('画布', () => {
  test.beforeEach(async ({ page, target }) => {
    const draft = draftOf(target)
    await openVersion(page, target, draft.id)
    await fitCanvas(page)
  })

  test('拖动节点：位置跟着走，松手后才提交（连线同步更新）', async ({ page, target }) => {
    const draft = draftOf(target)
    // 挑一个接了线的节点：拖动之后要能断言与它相连的那条线也重画了
    const mover =
      draft.nodes.find((node) =>
        draft.connections.some((connection) => connection.source_node_id === node.id),
      ) ?? draft.nodes[1]

    const card = nodeCard(page, mover.id)
    const before = await boxInView(card)
    const edgesBefore = await edgePaths(page)

    await dragBy(page, before, 110, 80)

    const after = await card.boundingBox()
    expect(after!.x).toBeGreaterThan(before.x + 60)
    expect(after!.y).toBeGreaterThan(before.y + 40)
    // 连线不是静止的旧路径：拖动结束后按新位置重画过
    expect(await edgePaths(page)).not.toEqual(edgesBefore)
  })

  test('契约⑤：位移不超过 2px 视为点击，打开节点配置弹窗', async ({ page, target }) => {
    const draft = draftOf(target)
    const node = draft.nodes.find((item) => item.node_type !== 'CONDITION') as GraphNode

    await dragBy(page, await boxInView(nodeCard(page, node.id)), 1, 1)

    await expect(page.locator('.el-dialog__title')).toContainText('编辑节点')
  })

  test('契约④：普通节点已有一条出线时，再拉一条会被拦下', async ({ page, target }) => {
    const draft = draftOf(target)
    const source = nodeWithOutgoing(draft.nodes, draft.connections)
    if (!source) test.skip(true, '草稿里没有已接出线的普通节点')
    const other = draft.nodes.find((node) => node.id !== source!.id) as GraphNode

    const card = nodeCard(page, source!.id)
    await card.hover()
    const port = card.locator('.flow__port--out')
    await expect(port).toBeVisible()

    const portBox = await boxInView(port)
    const otherBox = await boxInView(nodeCard(page, other.id))
    const edgesBefore = await page.locator('path.flow__edge[data-conn]').count()

    await page.mouse.move(portBox.x + portBox.width / 2, portBox.y + portBox.height / 2)
    await page.mouse.down()
    await page.mouse.move(
      otherBox.x + otherBox.width / 2,
      otherBox.y + otherBox.height / 2,
      { steps: 10 },
    )
    await page.mouse.up()

    // 要么"只能有一条去向"，要么"已经连过了"，总之不会静默新增一条
    await expect(
      page.locator('.el-message').filter({ hasText: /只能有一条去向|已经连过了/ }),
    ).toBeVisible()
    expect(await page.locator('path.flow__edge[data-conn]').count()).toBe(edgesBefore)
  })

  test('契约③：从「＋ 新增分支」的圆点拉线，新分支插在其余情况之前', async ({ page, target }) => {
    const draft = draftOf(target)
    const condition = draft.nodes.find((node) => node.node_type === 'CONDITION') as GraphNode
    // 新分支随便接一个节点都算数（这里优先选结束节点，语义最自然）
    const landing = (draft.nodes.find((node) => node.node_type === 'END') ??
      draft.nodes.find((node) => node.id !== condition.id)) as GraphNode

    const card = nodeCard(page, condition.id)
    // 兜底那条分支在 DOM 里不是最后一行 —— 后面还跟着「＋ 新增分支」
    const branches = card.locator('.flow__row:not(.flow__row--add)')
    const rowsBefore = await branches.count()

    await card.hover()
    const portBox = await boxInView(card.locator('.flow__row--add .flow__row-port'))
    const landingBox = await boxInView(nodeCard(page, landing.id))

    await page.mouse.move(portBox.x + portBox.width / 2, portBox.y + portBox.height / 2)
    await page.mouse.down()
    await page.mouse.move(landingBox.x + 10, landingBox.y + 10, { steps: 10 })
    await page.mouse.up()

    await expect(branches).toHaveCount(rowsBefore + 1)
    await expect(branches.last()).toContainText('其余情况')
  })

  test('面板拖入：落点是节点卡形态，新增后立刻弹配置窗', async ({ page }) => {
    const nodesBefore = await page.locator('.flow__stage .flow__node').count()
    const stage = await page.locator('.flow__stage').boundingBox()
    const item = paletteItem(page)

    // 面板项得能拖：真拖拽由浏览器发起，这里只能断言它具备条件
    await expect(item).toHaveAttribute('draggable', 'true')

    await dropPaletteItem(item, {
      x: Math.round(stage!.width / 2),
      y: Math.round(stage!.height - 40),
    })

    await expect(page.locator('.flow__stage .flow__node')).toHaveCount(nodesBefore + 1)
    await expect(page.locator('.el-dialog__title')).toContainText('新增节点')
  })

  test('删除节点：走确认弹窗删掉，而不是弹出编辑弹窗', async ({ page, target }) => {
    const draft = draftOf(target)
    const victim = draft.nodes.find(
      (node) => !['START', 'CONDITION'].includes(node.node_type),
    ) as GraphNode
    const card = nodeCard(page, victim.id)
    const nodesBefore = await page.locator('.flow__stage .flow__node').count()

    await card.hover()
    await card.locator('button[data-act="drop-node"]').click()

    // 卡片上的按钮必须自己处理点击：被画布当成"选中节点"的话这里会冒出编辑弹窗
    await expect(page.locator('.el-message-box')).toContainText('删除节点')
    await expect(page.locator('.el-dialog')).toHaveCount(0)

    await page.locator('.el-message-box button').filter({ hasText: '删除' }).click()

    await expect(page.locator('.flow__stage .flow__node')).toHaveCount(nodesBefore - 1)
    await expect(nodeCard(page, victim.id)).toHaveCount(0)
  })

  test('点条件分支的某一行：打开分支编辑器，不是节点配置窗', async ({ page, target }) => {
    const draft = draftOf(target)
    const condition = draft.nodes.find((node) => node.node_type === 'CONDITION') as GraphNode

    await nodeCard(page, condition.id).locator('.flow__row').first().click()

    await expect(page.locator('.el-dialog__title')).toContainText('条件分支 ·')
  })

  test('面板里的拖影在屏幕外，不会挤在面板上露出来', async ({ page }) => {
    const ghosts = page.locator('.flow-palette .flow-drag-ghost')
    await expect(ghosts).not.toHaveCount(0)

    const box = await ghosts.first().boundingBox()
    expect(box!.x + box!.width).toBeLessThan(0)
  })
})
