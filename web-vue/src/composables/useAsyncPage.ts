import { ref, shallowRef, type Ref } from 'vue'

/**
 * 页面的加载态与错误态。
 *
 * 对应旧版的 paint()：统一处理「正在读取数据 → 内容 / 整页错误面板」。
 * 旧版还要靠 renderGeneration 防竞态（快速切页时旧结果会覆盖新页面），
 * Vue 里有响应式就不需要了，但**重复调用 refresh 时仍以最后一次为准**：
 * 每次请求带一个序号，回来时序号不是最新就丢弃。
 */
export interface AsyncPage<T> {
  data: Ref<T>
  loading: Ref<boolean>
  error: Ref<Error | null>
  refresh: () => Promise<void>
}

/**
 * initial 是必填的：给一个同类型的空值（空数组 / null），data 就永远不是 undefined，
 * 页面里不必到处写 `?? []`。想要可空类型就传 `null as X | null`。
 */
export function useAsyncPage<T>(fetcher: () => Promise<T>, initial: T): AsyncPage<T> {
  const data = shallowRef<T>(initial)
  const loading = ref(false)
  const error = ref<Error | null>(null)
  let generation = 0

  async function refresh(): Promise<void> {
    const current = ++generation
    loading.value = true
    error.value = null
    try {
      const result = await fetcher()
      if (current !== generation) return
      data.value = result
    } catch (err) {
      if (current !== generation) return
      error.value = err instanceof Error ? err : new Error(String(err))
    } finally {
      if (current === generation) loading.value = false
    }
  }

  return { data, loading, error, refresh }
}
