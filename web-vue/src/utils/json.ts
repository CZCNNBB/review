/**
 * 解析用户填的 JSON。
 * 空串当空对象处理（表单里「不填就是没有」）；非法时抛出带中文前缀的错误，
 * 由调用方直接展示给用户（旧版靠这个文案挡住保存）。
 */
export function parseJsonInput(text: unknown, label: string): unknown {
  const trimmed = String(text ?? '').trim()
  if (!trimmed) return {}
  try {
    return JSON.parse(trimmed)
  } catch (err) {
    const reason = err instanceof Error ? err.message : String(err)
    return throwJsonError(`${label} 不是合法的 JSON：${reason}`)
  }
}

function throwJsonError(message: string): never {
  throw new Error(message)
}

/** 缩进 2 空格的 JSON 文本；循环引用等异常退回 String()。 */
export function stringifyJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

/** 空串/空值 → 兜底值，其余按 JSON 解析。 */
export function resolveJsonOrDefault(text: string | null | undefined, fallback: unknown): unknown {
  const trimmed = String(text ?? '').trim()
  if (!trimmed) return fallback
  return JSON.parse(trimmed)
}
