import { expect, test as base, type Locator, type Page } from '@playwright/test'

import { BASE_URL } from './urls'

/**
 * 端到端用例的前置条件：一个连得上的真后端。
 *
 * 示例数据模式去掉之后，这层不再有任何内置数据来源，跑之前要用环境变量指明目标：
 *
 *   E2E_BACKEND=http://127.0.0.1:8090    E2E_ADMIN_KEY=<后端 .env 里的 APPROVAL_ADMIN_KEY>
 *
 * 用例需要的节点（普通节点、条件分支、结束）都从后端现有的图里**现找**，找不到就带着
 * 说明跳过 —— 不拿写死的 UUID 硬跑，也就不需要在库里预置固定数据。
 * 会写库的用例另要 E2E_ALLOW_WRITES=1：开发库是多人共用的。
 */

export interface E2EBackend {
  base: string
  adminKey: string
}

/** 图里的节点与连线，只取用例挑节点时用得到的字段。 */
export interface GraphNode {
  id: string
  node_type: string
  name: string
}

export interface GraphConnection {
  source_node_id: string
  target_node_id: string | null
}

export interface DraftSpec {
  id: string
  nodes: GraphNode[]
  connections: GraphConnection[]
}

export interface E2ETarget {
  backend: E2EBackend
  /** 有节点、且含条件分支节点的草稿版本；没有就是 null，画布用例会跳过。 */
  draft: DraftSpec | null
  /** 已发布版本（流程的当前版本），只读用例用。 */
  publishedId: string | null
}

/** pinia 持久化配置写在哪个键下（与 stores/config.ts 的 STORAGE_KEY 一致）。 */
const CONFIG_STORAGE_KEY = 'approval-console.config'

const MISSING_DRAFT =
  '后端里没有「≥2 个节点且含条件分支」的草稿版本，画布用例没有可操作的对象。' +
  '在控制台建一条流程、拉几个节点保存成草稿即可。'

export function backendFromEnv(): E2EBackend | null {
  const base = (process.env.E2E_BACKEND || '').replace(/\/+$/, '')
  const adminKey = process.env.E2E_ADMIN_KEY || ''
  return base && adminKey ? { base, adminKey } : null
}

/** 直连后端的 admin 接口，信封与页面里走的是同一套 {code,msg,data}。 */
async function admin<T>(backend: E2EBackend, path: string): Promise<T> {
  const response = await fetch(`${backend.base}${path}`, {
    headers: { 'X-Admin-Key': backend.adminKey },
  })
  if (!response.ok) throw new Error(`${path} 返回 HTTP ${response.status}`)
  const payload = (await response.json()) as { code: number; msg?: string; data: T }
  if (payload.code !== 0) throw new Error(`${path} 返回失败：${payload.msg ?? payload.code}`)
  return payload.data
}

export async function resolveTarget(): Promise<E2ETarget | null> {
  const backend = backendFromEnv()
  if (!backend) return null

  const processes = await admin<Array<{ draft_version_id: string | null; current_version_id: string | null }>>(
    backend,
    '/api/admin/processes?limit=200',
  )

  let draft: DraftSpec | null = null
  let publishedId: string | null = null

  for (const process of processes) {
    publishedId ??= process.current_version_id
    if (draft || !process.draft_version_id) continue
    const graph = await admin<{
      version_id: string
      nodes?: GraphNode[]
      orchestration?: { connections?: GraphConnection[] }
    }>(backend, `/api/admin/process-versions/${process.draft_version_id}/graph`)

    const nodes = graph.nodes ?? []
    if (nodes.length >= 2 && nodes.some((node) => node.node_type === 'CONDITION')) {
      draft = { id: graph.version_id, nodes, connections: graph.orchestration?.connections ?? [] }
    }
  }

  return { backend, draft, publishedId }
}

/**
 * 探测结果按 worker 缓存一次：每个用例各查一遍接口既慢又没有必要。
 * 失败不缓存 —— 否则一次网络抖动会被后续所有用例当成同一个错误重复抛出来。
 */
let probed: Promise<E2ETarget | null> | undefined

function targetOnce(): Promise<E2ETarget | null> {
  probed ??= resolveTarget().catch((error: unknown) => {
    probed = undefined
    throw error
  })
  return probed
}

export const test = base.extend<{ target: E2ETarget }>({
  // 这个 fixture 不依赖别的 fixture，但 Playwright 要求第一个参数必须是对象解构
  // eslint-disable-next-line no-empty-pattern
  target: async ({}, use) => {
    if (!backendFromEnv()) {
      test.skip(true, '未配置 E2E_BACKEND / E2E_ADMIN_KEY，跳过端到端用例')
    }
    const target = await targetOnce()
    if (!target) test.skip(true, 'E2E_BACKEND 指向的后端连不上或密钥不对')
    await use(target as E2ETarget)
  },
})

/** 取草稿版本，没有就跳过当前用例。 */
export function draftOf(target: E2ETarget): DraftSpec {
  if (!target.draft) test.skip(true, MISSING_DRAFT)
  return target.draft as DraftSpec
}

/** 取已发布版本，没有就跳过当前用例。 */
export function publishedOf(target: E2ETarget): string {
  if (!target.publishedId) test.skip(true, '这条流程还没有已发布版本')
  return target.publishedId as string
}

/**
 * 把接口地址与密钥塞进 localStorage（启动时 pinia 会读它），省得每个用例都去顶栏填一遍。
 *
 * 两处都要写：`addInitScript` 管的是**下一次文档加载**，而页面已经加载过时，
 * 只改 hash 的导航不会重新加载文档，store 里的还是老值 —— 这时得直接写当前文档。
 */
export async function primeConfig(page: Page, target: E2ETarget): Promise<void> {
  const value = JSON.stringify({
    base: target.backend.base,
    adminKey: target.backend.adminKey,
    apiKey: '',
  })
  await page.addInitScript(
    ({ key, next }) => window.localStorage.setItem(key, next),
    { key: CONFIG_STORAGE_KEY, next: value },
  )
  // about:blank 上没有 localStorage，跳过
  if (page.url().startsWith('http')) {
    await page.evaluate(
      ({ key, next }) => window.localStorage.setItem(key, next),
      { key: CONFIG_STORAGE_KEY, next: value },
    )
  }
}

/** 打开某个版本的编辑器。 */
export async function openVersion(
  page: Page,
  target: E2ETarget,
  versionId: string,
): Promise<void> {
  await primeConfig(page, target)
  // 走绝对地址：这个函数在 globalSetup 里也会被用到，那时没有 test 的 baseURL
  await page.goto(`${BASE_URL}/#/versions/${versionId}`)
  await expect(page.locator('.flow__stage .flow__node').first()).toBeVisible()
}

/** 画布里的真节点。左侧面板里每个定义都有一张屏幕外的拖影，别把它数进来。 */
export function nodeCard(page: Page, nodeId: string) {
  return page.locator(`.flow__stage .flow__node[data-id="${nodeId}"]`)
}

/** 面板里可以拖的节点（跳过「开始」—— 一条流程只能有一个）。 */
export function paletteItem(page: Page) {
  return page.locator('.flow-palette__item:not(.is-disabled):not(:has-text("开始"))').first()
}

/**
 * 画布是可滚动的：先把它滚进可视区再取坐标。
 * 直接 boundingBox() 拿到的可能是被裁在可视区外的位置，鼠标点过去会落在别的元素上。
 */
export async function boxInView(locator: Locator): Promise<{
  x: number
  y: number
  width: number
  height: number
}> {
  await locator.scrollIntoViewIfNeeded()
  const box = await locator.boundingBox()
  if (!box) throw new Error('元素不在页面上，取不到坐标')
  return box
}

/** 点「适应」把整张图缩进可视区。不先做这一步，边上的节点会有一半在视口外。 */
export async function fitCanvas(page: Page): Promise<void> {
  await page.locator('button[title="适应画布"]').click()
}

/**
 * 把面板里的节点拖到画布上的某个点（点在画布坐标系里给）。
 *
 * 合成页面内的 DragEvent，而不是用 Playwright 的 dragTo：本机 Chromium 上 dragTo
 * 一个 drag 事件都不发（dragstart/dragover/drop 全无），而 DataTransfer 只存在于真浏览器，
 * 没法退回 jsdom。合成跑的是应用自己那一整套 —— dragstart 里 setData + setDragImage +
 * emit('drag-start')，dragover 里算落点虚线，drop 里读 dataTransfer 建节点。
 * 「浏览器会不会替你把拖拽发起来」属于浏览器行为，由 draggable 属性的断言兜着。
 */
export async function dropPaletteItem(
  item: Locator,
  point: { x: number; y: number },
): Promise<void> {
  await item.evaluate(
    (source, arg) => {
      const target = document.querySelector(arg.selector) as HTMLElement | null
      if (!target) throw new Error(`找不到落点元素 ${arg.selector}`)
      const rect = target.getBoundingClientRect()
      const clientX = rect.left + arg.x
      const clientY = rect.top + arg.y
      const dataTransfer = new DataTransfer()
      const fire = (element: EventTarget, type: string) =>
        element.dispatchEvent(
          new DragEvent(type, { bubbles: true, cancelable: true, dataTransfer, clientX, clientY }),
        )
      fire(source, 'dragstart')
      fire(target, 'dragover')
      fire(target, 'drop')
      fire(source, 'dragend')
    },
    { selector: '.flow__stage', x: point.x, y: point.y },
  )
}

/** 所有连线的形状，用来断言"重画过了"。 */
export function edgePaths(page: Page): Promise<string[]> {
  return page
    .locator('path[data-conn]')
    .evaluateAll((elements) =>
      elements.map((element) => element.getAttribute('d') ?? '').sort(),
    )
}

/** 在卡片上按住、移动、松手。位移决定它算点击还是拖拽（契约⑤）。 */
export async function dragBy(
  page: Page,
  box: { x: number; y: number },
  dx: number,
  dy: number,
): Promise<void> {
  await page.mouse.move(box.x + 30, box.y + 20)
  await page.mouse.down()
  await page.mouse.move(box.x + 30 + dx, box.y + 20 + dy, { steps: 8 })
  await page.mouse.up()
}
