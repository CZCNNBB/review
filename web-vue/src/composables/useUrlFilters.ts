import { computed, type WritableComputedRef } from 'vue'
import { useRoute, useRouter } from 'vue-router'

/**
 * 筛选条件读写到地址栏。
 *
 * 旧版就把它编码在 hash 里（#/tasks?status=ALL），保持这个行为：刷新、后退、
 * 把链接发给别人，看到的都是同一份筛选结果。组件里只读这个 ref，不维护第二份真相。
 */
export function useUrlFilters(): {
  read: (key: string) => string
  write: (values: Record<string, string | null | undefined>) => void
  filter: (key: string, fallback?: string) => WritableComputedRef<string>
} {
  const route = useRoute()
  const router = useRouter()

  function read(key: string): string {
    const value = route.query[key]
    return typeof value === 'string' ? value : ''
  }

  function write(values: Record<string, string | null | undefined>): void {
    const query = { ...route.query }
    Object.entries(values).forEach(([key, value]) => {
      if (value === null || value === undefined || value === '') delete query[key]
      else query[key] = value
    })
    router.replace({ query })
  }

  function filter(key: string, fallback = ''): WritableComputedRef<string> {
    return computed({
      get: () => read(key) || fallback,
      set: (value: string) => write({ [key]: value === fallback ? null : value }),
    })
  }

  return { read, write, filter }
}
