import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  // 产物最终挂在后端 /console 下。用相对路径让资源前缀无关，换个挂载点不用重新构建。
  base: './',
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // 显式绑 IPv4：默认的 localhost 在 Windows 上可能只监听 ::1，
    // 而 Playwright 的 webServer 探活与脚本里都用 127.0.0.1，会连不上。
    host: '127.0.0.1',
    port: 5173,
  },
  build: {
    // 两个组件库合计体积不小，警告阈值调高，避免每次构建都刷无意义的提示。
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        // 把两个组件库单独切出来：它们变动频率远低于业务代码，利于浏览器缓存。
        manualChunks(id: string) {
          if (id.includes('node_modules/element-plus')) return 'element-plus'
          if (id.includes('node_modules/ant-design-vue')) return 'ant-design-vue'
          return undefined
        },
      },
    },
  },
})
