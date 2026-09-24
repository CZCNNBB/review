/** 接口错误。status 为 0 表示请求根本没发出去（缺密钥、连不上）。 */
export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/**
 * 把后端的错误体翻成一句能直接显示给用户的中文。
 *
 * 后端有三种 detail 形态：字符串、FastAPI 的校验数组、以及带 issues 的业务对象
 * （流程校验失败就是这种）。三种都要认，否则用户只会看到「请求失败」。
 */
export function detailMessage(payload: unknown, status: number): string {
  const detail = (payload as { detail?: unknown } | null)?.detail

  if (typeof detail === 'string') return detail

  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const entry = item as { loc?: unknown[]; msg?: string }
        return `${(entry.loc || []).join('.')}：${entry.msg ?? ''}`
      })
      .join('；')
  }

  if (detail && typeof detail === 'object') {
    const entry = detail as {
      message?: string
      issues?: Array<{ message?: string; field?: string }>
    }
    let message = entry.message || '请求未通过校验'
    if (Array.isArray(entry.issues) && entry.issues.length) {
      const parts = entry.issues.map((issue) =>
        issue.field ? `${issue.message}（${issue.field}）` : String(issue.message ?? ''),
      )
      message += `：${parts.join('；')}`
    }
    return message
  }

  if (status === 401) return '认证失败，请检查密钥是否正确'
  if (status === 403) return '当前身份没有访问该资源的权限'
  if (status === 404) return '目标资源不存在'
  if (status === 503) return '服务端配置不完整，接口暂不可用'
  return `请求失败（HTTP ${status}）`
}
