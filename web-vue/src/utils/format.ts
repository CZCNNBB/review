import dayjs from 'dayjs'

const ORDER_MARKS = '①②③④⑤⑥⑦⑧⑨⑩'

/**
 * 时间格式化：`YYYY-MM-DD HH:mm`。
 * 空值给「—」；**非法输入原样返回**（旧版行为，dayjs 会给出 Invalid Date，必须显式判断）。
 */
export function formatTime(value?: string | null): string {
  if (!value) return '—'
  const parsed = dayjs(value)
  if (!parsed.isValid()) return String(value)
  return parsed.format('YYYY-MM-DD HH:mm')
}

/** 耗时：毫秒 → 人话（毫秒 / 秒 / 分秒 / 小时分）。 */
export function formatDuration(ms?: number | null): string {
  if (ms === null || ms === undefined) return '—'
  if (ms < 1000) return `${ms} 毫秒`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)} 秒`
  const minutes = Math.floor(ms / 60000)
  if (minutes < 60) return `${minutes} 分 ${Math.round((ms % 60000) / 1000)} 秒`
  return `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分`
}

/** 长 ID 只显示前 8 位。 */
export function shortId(value?: string | null): string {
  if (!value) return '—'
  return String(value).slice(0, 8)
}

/** 分支行序号：①②③…，超过十行退回 `11.` 这种写法。 */
export function orderMark(position: number): string {
  return ORDER_MARKS[position - 1] || `${position}.`
}

/** 密钥打码：保留前 12 位与后 4 位，中间用点代替。 */
export function maskSecret(value: string): string {
  if (!value) return ''
  if (value.length <= 16) return value
  return `${value.slice(0, 12)}${'•'.repeat(6)}${value.slice(-4)}`
}
