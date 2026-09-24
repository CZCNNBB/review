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
    '/grants',
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
  await primeConfig(page, target)
  await page.goto('/#/processes')

  // 等表格真的出结果再数：加载中就直接判"没有行"的话，用例会假装跳过
  await expect(page.locator('td.is-actions, .ant-empty')).not.toHaveCount(0)

  const actions = page.locator('td.is-actions').first()
  if ((await actions.count()) === 0) test.skip(true, '这个后端里没有带操作列的行')
  await expect(actions).toBeVisible()

  const links = actions.locator('.btn--link')
  const count = await links.count()
  if (count < 2) test.skip(true, '这一行只有一个操作按钮，量不出间距')

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

test('查不到的 id 给整页失败态，而不是白屏', async ({ page, target }) => {
  await primeConfig(page, target)

  await page.goto('/#/tenants/00000000-0000-4000-8000-000000000000')

  await expect(page.locator('.ant-result-title')).toContainText('读取失败')
  await expect(page.locator('.ant-result-subtitle')).not.toBeEmpty()
})
