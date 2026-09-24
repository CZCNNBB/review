import { defineConfig, devices } from '@playwright/test'

/**
 * 端到端测试：跑真浏览器。
 *
 * 只为 jsdom 里物理上测不了的几件事而存在：
 *   - HTML5 拖拽（DataTransfer 在 jsdom 里不存在）
 *   - 拉线落点（document.elementFromPoint 在 jsdom 里永远返回 null）
 *   - 指针捕获 + 缩放补偿的真实坐标
 *   - 两个组件库共存时的浮层层级（只有真实 CSS 才成立）
 *
 * 这一层要一个连得上的真后端，用环境变量指过去（详见 e2e/backend.ts）：
 *   E2E_BACKEND=http://127.0.0.1:8090  E2E_ADMIN_KEY=<后端的 APPROVAL_ADMIN_KEY>
 * 没配就整体跳过，不会假装跑过了。
 */
const PORT = Number(process.env.E2E_PORT || 5199)
const BASE_URL = `http://127.0.0.1:${PORT}`

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  reporter: process.env.CI ? 'line' : 'list',
  use: {
    // 端口可用环境变量覆盖：本地同时开着别的 dev server 时换个口跑
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    viewport: { width: 1440, height: 900 },
  },
  projects: [
    {
      name: 'chromium',
      // 用完整的 chromium（channel）而不是 headless shell：一是本机已有这个二进制，
      // 二是它对 CSS/浮层的渲染与真实用户浏览器更接近，正好是这层要验证的东西。
      use: { ...devices['Desktop Chrome'], channel: 'chromium' },
    },
  ],
  webServer: {
    command: `npm run dev -- --port ${PORT} --strictPort`,
    url: BASE_URL,
    reuseExistingServer: true,
    timeout: 60_000,
  },
})
