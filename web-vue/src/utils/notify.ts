import { ElMessage } from 'element-plus'

/**
 * 全局提示。旧版是 toast(message, kind)，这里保持同样的语义与时长：
 * 错误 6 秒、其余 3.2 秒（错误要多留一会儿，用户得看清原因）。
 *
 * 不做成 Pinia store：ElMessage 自己就是单例队列，没有需要跨组件共享的可变状态。
 * 唯一值得留的口子是 setSink —— 单测里可以断言提示内容，而不必真的渲染 DOM。
 */
export type NotifyKind = 'ok' | 'err'

type Sink = (message: string, kind: NotifyKind) => void

let sink: Sink | null = null

export function setNotifySink(next: Sink | null): void {
  sink = next
}

export function notify(message: string, kind: NotifyKind = 'ok'): void {
  if (sink) {
    sink(message, kind)
    return
  }
  ElMessage({
    message,
    type: kind === 'err' ? 'error' : 'success',
    duration: kind === 'err' ? 6000 : 3200,
    showClose: true,
  })
}

/** 常量的语义化包装，读代码时不用猜 kind。 */
export const toastOk = (message: string) => notify(message, 'ok')
export const toastError = (message: string) => notify(message, 'err')
