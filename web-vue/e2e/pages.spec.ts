import { expect } from '@playwright/test'

import { primeConfig, test } from './backend'

/**
 * 每个页面都用真后端打开一遍。
 *
 * 这一层挡的是"整页白屏 / 整页失败态 / 运行时报错"这类只在真数据下才暴露的问题 ——
 * 12 个页面里只有版本编辑器有专门的用例，其余的在这条之前没有任何覆盖。
 * 用例自己按接口现取 id，所以不依赖库里预置了哪些数据。
 */

async function admin<T>(base: string, key: string, path: string): Promise<T> {
  const response = await fetch(`${base}${path}`, { headers: { 'X-Admin-Key': key } })
  const payload = (await response.json()) as { code: number; msg?: string; data: T }
  if (payload.code !== 0) throw new Error(`${path} 返回失败：${payload.msg ?? payload.code}`)
  return payload.data
}

test('每个页面都能打开，没有整页失败态、没有运行时报错', async ({ page, target }) => {
  const { base, adminKey } = target.backend
  const tenants = await admin<Array<{ id: string }>>(base, adminKey, '/api/admin/tenants?limit=5')
  const processes = await admin<Array<{ id: string }>>(base, adminKey, '/api/admin/processes?limit=5')
  const executions = await admin<Array<{ id: string }>>(
    base,
    adminKey,
    '/api/admin/execution-records?limit=5',
  )

  const paths = [
    '/overview',
    '/tenants',
    '/people',
    '/processes',
    '/definitions',
    '/actions',
    '/tasks',
    '/start',
    '/executions',
    '/usages',
    ...(tenants[0] ? [`/tenants/${tenants[0].id}`] : []),
    ...(processes[0] ? [`/processes/${processes[0].id}`] : []),
    ...(executions[0] ? [`/executions/${executions[0].id}`] : []),
  ]

  const crashes: string[] = []
  page.on('pageerror', (error) => crashes.push(error.message))

  await primeConfig(page, target)

  for (const path of paths) {
    await page.goto(`/#${path}`)
    // 整页失败态（ErrorPanel）就是"这个页面没起来"
    await expect(page.locator('.ant-result-title'), `${path} 出现了整页失败态`).toHaveCount(0)
  }

  expect(crashes, '页面有未捕获的异常').toEqual([])
})

/**
 * 操作列的按钮挤在一起是真实发生过的：旧版靠 HTML 里的换行当分隔符，而 Vue 编译模板
 * 会把元素之间的空白删掉（whitespace: 'condense'），照搬过来几个按钮就贴在一坨。
 * 这条按实际坐标量间距，css 改动把它弄丢了会立刻红。
 */
test('列表页的操作列：按钮之间有间距，且排在一条线上', async ({ page, target }) => {
  // 有没有数据按接口判断，不靠读 DOM：表格在加载期也渲染空态，
  // 拿"有没有行"当跳过条件会读到加载中的空表，用例就假装跳过了。
  const processes = await admin<Array<unknown>>(
    target.backend.base,
    target.backend.adminKey,
    '/api/admin/processes?limit=5',
  )
  if (!processes.length) test.skip(true, '这个后端里没有审批流，量不出操作列间距')

  await primeConfig(page, target)
  await page.goto('/#/processes')

  const actions = page.locator('td.is-actions').first()
  await expect(actions).toBeVisible()

  const links = actions.locator('.btn--link')
  const count = await links.count()
  // 详情 / 复制 / 停用 三个里至少有两个；真只剩一个说明列渲染出问题了
  expect(count, '操作列里的按钮少于两个，量不出间距').toBeGreaterThan(1)

  const boxes = []
  for (let index = 0; index < count; index += 1) boxes.push((await links.nth(index).boundingBox())!)

  // 同一行看的是竖直中心：<a> 是 inline，<button> 是 inline-block，
  // 两者的盒子上沿本来就不一定齐，差个一两像素不算换行。
  const centerOf = (box: { y: number; height: number }): number => box.y + box.height / 2

  for (let index = 1; index < boxes.length; index += 1) {
    const gap = boxes[index].x - (boxes[index - 1].x + boxes[index - 1].width)
    expect(gap, `第 ${index} 个按钮和上一个之间没有间距`).toBeGreaterThan(4)
    expect(
      Math.abs(centerOf(boxes[index]) - centerOf(boxes[0])),
      '操作按钮应当排在同一行',
    ).toBeLessThan(4)
  }
})

/**
 * 授权并进租户详情页之后，这里挡两件事：两块面板真的在页面上，以及旧的 #/grants
 * 链接不会掉进 404（收藏夹和文档里还有它）。
 *
 * 不假设这个租户已经有多少条授权 —— 有行就验行内的启用/停用按钮，没行就验空态，
 * 换一个后端也能跑。
 */
test('租户详情页里有审批流与业务动作授权两块面板', async ({ page, target }) => {
  const tenants = await admin<Array<{ id: string }>>(
    target.backend.base,
    target.backend.adminKey,
    '/api/admin/tenants?limit=5',
  )
  if (!tenants[0]) test.skip(true, '这个后端里还没有租户')

  await primeConfig(page, target)
  await page.goto(`/#/tenants/${tenants[0].id}`)

  const processPanel = page.locator('.panel', { hasText: '审批流授权' })
  const actionPanel = page.locator('.panel', { hasText: '业务动作授权' })
  await expect(processPanel.getByText('审批流授权', { exact: true })).toBeVisible()
  await expect(actionPanel.getByText('业务动作授权', { exact: true })).toBeVisible()

  for (const panel of [processPanel, actionPanel]) {
    const rows = panel.locator('tbody tr.ant-table-row')
    if ((await rows.count()) === 0) {
      await expect(panel.locator('.ant-empty')).toBeVisible()
      continue
    }
    // 有授权时行内必须能停用/启用，否则只能看不能管
    await expect(rows.first().getByRole('button', { name: /停用|启用/ })).toBeVisible()
  }

  // 旧链接落到租户列表，不是 404
  await page.goto('/#/grants')
  await expect(page).toHaveURL(/#\/tenants$/)
})

/**
 * API Key 与回调凭据的有效状态是 ACTIVE（撤销后 REVOKED），不是 ENABLED。
 * 前端曾经拿 ENABLED 去比，"撤销"按钮从来没渲染出来过，未撤销的行还被文案说成"已撤销"。
 */
test('租户详情页里有效的密钥与凭据都能撤销', async ({ page, target }) => {
  const { base, adminKey } = target.backend
  const tenants = await admin<Array<{ id: string }>>(base, adminKey, '/api/admin/tenants?limit=5')
  if (!tenants[0]) test.skip(true, '这个后端里还没有租户')
  const tenantId = tenants[0].id

  const [apiKeys, credentials] = await Promise.all([
    admin<Array<{ status: string }>>(base, adminKey, `/api/admin/tenants/${tenantId}/api-keys`),
    admin<Array<{ status: string }>>(
      base,
      adminKey,
      `/api/admin/tenants/${tenantId}/callback-credentials`,
    ),
  ])

  await primeConfig(page, target)
  await page.goto(`/#/tenants/${tenantId}`)

  // 按面板标题定位，不用 hasText 匹配整块面板：正文里到处都会提到 "API Key"
  const panelOf = (title: string) =>
    page.locator('.panel').filter({ has: page.locator('.panel__title', { hasText: title }) })

  let checked = 0
  for (const [title, rows] of [
    ['API Key', apiKeys],
    ['回调 Service Token', credentials],
  ] as const) {
    const activeIndex = rows.findIndex((row) => row.status === 'ACTIVE')
    if (activeIndex < 0) continue
    await expect(
      panelOf(title)
        .locator('tbody tr.ant-table-row')
        .nth(activeIndex)
        .getByRole('button', { name: '撤销' }),
      `${title} 里有效的那一行应该能撤销`,
    ).toBeVisible()
    checked += 1
  }

  // 两个面板都没有有效凭据的话，这条用例什么也没验到，不能算通过
  expect(checked, '这个租户没有有效的密钥或凭据，验不了撤销入口').toBeGreaterThan(0)
})

/**
 * 契约⑧：管理台按「租户 → 有效 API Key」自动借用租户密钥。
 * 密钥的有效状态是 ACTIVE，前端曾经拿 ENABLED 去比 —— 结果永远借不到，
 * 这一页只会提示"没有可用的租户 API Key"。
 */
test('发起审批页能自动借到租户的密钥并验证通过', async ({ page, target }) => {
  const { base, adminKey } = target.backend
  const tenants = await admin<Array<{ id: string }>>(base, adminKey, '/api/admin/tenants?limit=5')
  if (!tenants[0]) test.skip(true, '这个后端里还没有租户')

  const keys = await admin<Array<{ status: string }>>(
    base,
    adminKey,
    `/api/admin/tenants/${tenants[0].id}/api-keys`,
  )
  if (!keys.some((key) => key.status === 'ACTIVE')) test.skip(true, '这个租户没有有效密钥')

  await primeConfig(page, target)
  await page.goto(`/#/start?tenant=${tenants[0].id}`)

  // 借到密钥之后页面会拿它去 /api/tenant/context 实打实验一次，验过才显示这一行
  await expect(page.getByText(/密钥已验证/)).toBeVisible()
})

test('查不到的 id 给整页失败态，而不是白屏', async ({ page, target }) => {
  await primeConfig(page, target)

  await page.goto('/#/tenants/00000000-0000-4000-8000-000000000000')

  await expect(page.locator('.ant-result-title')).toContainText('读取失败')
  await expect(page.locator('.ant-result-subtitle')).not.toBeEmpty()
})
