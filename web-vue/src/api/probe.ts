import axios from 'axios'

import { useConfigStore, type LinkState } from '@/stores/config'

/**
 * 顶栏「测试连接」：拿一个最轻的管理接口探活，只判断连通与密钥是否被接受。
 *
 * 这里刻意不走 api/http.ts 的统一客户端 —— 探活本身要能在客户端尚未初始化、
 * 密钥可能为空的状态下工作，而且要吞掉错误只回一个三态结果。
 */
export async function probeConnection(): Promise<LinkState> {
  const config = useConfigStore()
  if (!config.adminKey) return 'off'

  try {
    await axios.get(`${config.normalizedBase}/api/admin/tenants`, {
      params: { limit: 1 },
      headers: { 'X-Admin-Key': config.adminKey },
      timeout: 8000,
    })
    return 'ok'
  } catch {
    return 'off'
  }
}
