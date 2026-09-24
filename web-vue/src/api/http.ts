import axios, { AxiosError, type AxiosResponse } from 'axios'

import { useConfigStore } from '@/stores/config'

import { ApiError, detailMessage } from './errors'

/** 用哪个身份调用：管理台密钥（X-Admin-Key）还是租户密钥（X-API-Key）。 */
export type AuthKind = 'admin' | 'apikey'

declare module 'axios' {
  export interface AxiosRequestConfig {
    /** 用哪个身份调用。名字不带 auth —— axios 自己的 auth 是 HTTP Basic 凭据。 */
    authKind?: AuthKind
    /** authKind='apikey' 时临时指定密钥，不传则用配置里的。 */
    apiKey?: string
  }
}

/**
 * 全局请求实例。
 *
 * 统一处理三件事：
 * 1. baseURL 每次请求都从 store 取（用户在顶栏改了地址要立刻生效）；
 * 2. 按 auth 注入 X-Admin-Key / X-API-Key，没有密钥就在发请求前拦下；
 * 3. 拆掉后端的 `{code, msg, data}` 信封，让调用方直接拿 data，并把所有失败
 *    归一成 ApiError（带 status 与中文文案）。
 */
export const http = axios.create({ timeout: 20000 })

http.interceptors.request.use((config) => {
  const app = useConfigStore()
  config.baseURL = app.normalizedBase
  config.headers = config.headers ?? {}

  if ((config.authKind ?? 'admin') === 'admin') {
    if (app.adminKey) config.headers['X-Admin-Key'] = app.adminKey
    else throw new ApiError('请先在顶部填写管理密钥（X-Admin-Key）', 0)
  } else {
    const key = config.apiKey || app.apiKey
    if (key) config.headers['X-API-Key'] = key
    else throw new ApiError('没有找到可用的租户 API Key，请先在租户页面签发一个', 0)
  }
  return config
})

http.interceptors.response.use(
  (response: AxiosResponse) => {
    const payload = response.data
    if (payload && typeof payload === 'object' && 'code' in payload) {
      const envelope = payload as { code: number; msg?: string; data?: unknown }
      if (envelope.code !== 0) {
        throw new ApiError(envelope.msg || '接口返回失败', response.status)
      }
      response.data = envelope.data
    }
    return response
  },
  (error: AxiosError) => throwApiError(error),
)

function throwApiError(error: AxiosError): never {
  if (error.response) {
    throw new ApiError(
      detailMessage(error.response.data, error.response.status),
      error.response.status,
    )
  }
  const app = useConfigStore()
  throw new ApiError(`无法连接 ${app.base}，请确认后端已启动`, 0)
}

/** 四个动词的薄封装，返回拆过信封的业务数据。 */
export const api = {
  get: <T>(path: string, auth: AuthKind = 'admin', apiKey?: string): Promise<T> =>
    http.get<T>(path, { authKind: auth, apiKey }).then((response) => response.data),

  post: <T>(path: string, body?: unknown, auth: AuthKind = 'admin', apiKey?: string): Promise<T> =>
    http.post<T>(path, body, { authKind: auth, apiKey }).then((response) => response.data),

  patch: <T>(path: string, body?: unknown, auth: AuthKind = 'admin'): Promise<T> =>
    http.patch<T>(path, body, { authKind: auth }).then((response) => response.data),

  put: <T>(path: string, body?: unknown, auth: AuthKind = 'admin'): Promise<T> =>
    http.put<T>(path, body, { authKind: auth }).then((response) => response.data),
}

/** 局部失败不阻塞整页：概览这类聚合页每个分区各自兜底成空值。 */
export async function safe<T>(promise: Promise<T>, fallback: T): Promise<T> {
  try {
    return await promise
  } catch {
    return fallback
  }
}
