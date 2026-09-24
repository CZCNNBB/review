import { chromium } from '@playwright/test'

import { backendFromEnv, openVersion, resolveTarget } from './backend'

/**
 * 先自己把编辑器页走一遍，把开发服务器预热。
 *
 * 第一次打开某个路由时 Vite 才现编译那个 chunk（编辑器是最大的一块）。十几个 worker
 * 同时开跑正好撞上这次编译，首屏会被拖过 expect 的超时窗口 —— 表现出来就是
 * "编辑器打开了但没有节点"这种看起来像 bug 的失败。预热一次就没这回事了。
 *
 * 没配后端就直接返回：用例本来也会整体跳过。
 */
export default async function globalSetup(): Promise<void> {
  if (!backendFromEnv()) return

  const target = await resolveTarget()
  if (!target?.draft) return

  const browser = await chromium.launch({ channel: 'chromium' })
  try {
    const page = await browser.newPage()
    await openVersion(page, target, target.draft.id)
  } finally {
    await browser.close()
  }
}
