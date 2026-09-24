import { createRouter, createWebHashHistory } from 'vue-router'

import { registerGuards } from './guards'
import { routes } from './routes'

/**
 * 用 hash 模式：老版本的链接（#/tenants、#/versions/xxx）全部继续可用，
 * 而且挂在后端任意路径下都不需要服务端做 history fallback。
 */
export const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

// 离开版本编辑器时丢弃工作副本（契约①）
registerGuards(router)

export { routes }
