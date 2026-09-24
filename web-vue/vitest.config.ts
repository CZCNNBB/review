import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    // 组件测试需要 DOM；纯函数测试跑在同一个环境里没有副作用。
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    include: ['src/**/*.spec.ts', 'tests/**/*.spec.ts'],
    // e2e 目录归 Playwright 管，别让 Vitest 收进去
    exclude: ['node_modules/**', 'e2e/**'],
  },
})
