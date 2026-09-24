import { toastError, toastOk } from '@/utils/notify'

/**
 * 复制到剪贴板。
 *
 * navigator.clipboard 在非安全上下文（http 的局域网地址就是）拿不到，退回
 * 旧版的 textarea + execCommand 兜底方案。
 */
export async function copyText(text: string, successMessage = '已复制到剪贴板'): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
    toastOk(successMessage)
  } catch {
    if (fallbackCopy(text)) toastOk(successMessage)
    else toastError('复制失败，请手动选中复制')
  }
}

function fallbackCopy(text: string): boolean {
  const area = document.createElement('textarea')
  area.value = text
  area.style.position = 'fixed'
  area.style.opacity = '0'
  document.body.appendChild(area)
  try {
    area.select()
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    document.body.removeChild(area)
  }
}
