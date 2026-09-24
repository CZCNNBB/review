import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * 左侧导航的计数徽标与当前高亮项。
 * 计数由各页面在自己加载完数据后写入，导航是常驻组件，所以放 store 里。
 */
export const useShellStore = defineStore('shell', () => {
  /** 导航项 key → 计数；没有计数就不显示徽标。 */
  const counts = ref<Record<string, number>>({})

  function setCount(key: string, value: number): void {
    counts.value = { ...counts.value, [key]: value }
  }

  function setCounts(next: Record<string, number>): void {
    counts.value = { ...counts.value, ...next }
  }

  return { counts, setCount, setCounts }
})
