import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

/** 连接状态：未探测 / 连通 / 密钥无效或连接失败。 */
export type LinkState = 'idle' | 'ok' | 'off'

/** 控制台的接口配置，持久化在浏览器里，不上传。 */
export const STORAGE_KEY = 'approval-console.config'

/**
 * 默认接口地址：被后端托管时（页面挂在 /console 下）用同源地址，开发期退回本地 8090。
 * 这样部署后不用手填，本地 `npm run dev` 也不用改配置。
 */
function defaultBase(): string {
  if (typeof window === 'undefined') return 'http://127.0.0.1:8090'
  const { origin, pathname } = window.location
  if (origin.startsWith('http') && !/^https?:\/\/localhost(:\d+)?$/.test(origin)) return origin
  if (origin.startsWith('http') && pathname.includes('/console')) return origin
  return 'http://127.0.0.1:8090'
}

export const useConfigStore = defineStore(
  'config',
  () => {
    /** 后端地址，允许带尾斜杠。 */
    const base = ref(defaultBase())
    /** 管理员密钥，请求头 X-Admin-Key。 */
    const adminKey = ref('')
    /** 租户密钥，请求头 X-API-Key；多数场景由 credentials store 自动借用。 */
    const apiKey = ref('')
    /** 顶栏的连接状态点。 */
    const linkState = ref<LinkState>('idle')
    /** 去掉尾斜杠后的接口地址，拼路径时用。 */
    const normalizedBase = computed(() => base.value.replace(/\/+$/, ''))

    function setBase(next: string): void {
      const trimmed = next.trim()
      base.value = trimmed === '' ? defaultBase() : trimmed
      linkState.value = 'idle'
    }

    function setAdminKey(next: string): void {
      adminKey.value = next.trim()
      linkState.value = 'idle'
    }

    function setApiKey(next: string): void {
      apiKey.value = next.trim()
    }

    function setLinkState(next: LinkState): void {
      linkState.value = next
    }

    return {
      base,
      adminKey,
      apiKey,
      linkState,
      normalizedBase,
      setBase,
      setAdminKey,
      setApiKey,
      setLinkState,
    }
  },
  {
    persist: {
      key: STORAGE_KEY,
      pick: ['base', 'adminKey', 'apiKey'],
    },
  },
)
